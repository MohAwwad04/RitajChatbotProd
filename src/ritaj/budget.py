"""Daily provider budget — spend the free allowance deliberately, not by surprise.

Cloudflare's free Workers AI allocation is 10,000 **neurons** per day. Neurons
are what the provider actually meters and what the dashboard shows, so that is
what this budget counts.

## Why not count answers

The first version counted answers: one `budget.consume()` per reply, with a
limit of 180. That was wrong twice.

  * **It missed calls.** `generate.condense()` makes its own provider call to
    rewrite a follow-up into a standalone question. Every follow-up therefore
    cost two calls and was billed as one, so the budget silently under-counted
    on exactly the traffic a real conversation produces.
  * **It assumed a fixed price.** A request's cost is dominated by its prompt.
    A short question with no history costs a fraction of a long one with six
    turns of context and a full source set — counting them the same is wrong by
    close to an order of magnitude in either direction.

Metering the provider's own `usage` block fixes both: the count is taken where
the call happens (`llm.py`), so nothing can forget to report, and it is
proportional to what is actually spent.

## The conversion

Cloudflare publishes Gemma 4 26B A4B at **$0.10 per million input tokens** and
**$0.30 per million output tokens** (verified 2026-08-05), and Workers Paid
bills neurons at **$0.011 per 1,000**. So:

    input   $0.10/M  ÷ $0.011/1000  =   9,091 neurons per million input tokens
    output  $0.30/M  ÷ $0.011/1000  =  27,273 neurons per million output tokens

A representative RAG request — 4,000 input + 500 output tokens — is therefore
about 36 + 14 = **50 neurons**, and the 10,000/day allowance is roughly 200 such
answers. Both rates are configurable, because a provider price change would
otherwise silently invalidate the budget.

Note: Cloudflare does not publish a neurons-per-token figure for this model
directly; the values above are derived from its published dollar prices. There
have been community reports of billing discrepancies on this model, so treat the
budget as a guard rail and reconcile against the provider dashboard during the
pilot rather than trusting it as an exact meter.

Counting is in-process and resets at UTC midnight. A restart loses the count,
which is the safe direction: the provider's own limit is still there as a
backstop, and a restarted service that refused to answer would be worse.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from . import errors
from .config import settings

_lock = threading.Lock()
_day: str | None = None
_neurons = 0.0
_calls = 0

# Rough characters-per-token for the fallback estimate. Deliberately low (i.e.
# pessimistic — more estimated tokens) because Arabic encodes to noticeably more
# tokens per character than English on these tokenizers, and a budget that
# under-estimates is a budget that overruns.
_CHARS_PER_TOKEN = 3.0


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_to_reset() -> int:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((midnight.timestamp() + 86400) - now.timestamp())


def neurons_for(prompt_tokens: int, completion_tokens: int) -> float:
    """Neuron cost of one call, from the configured per-million rates."""
    return (
        prompt_tokens / 1_000_000 * settings.neurons_per_m_input
        + completion_tokens / 1_000_000 * settings.neurons_per_m_output
    )


def estimate_tokens(text: str) -> int:
    """Token estimate for providers that report no usage (Ollama, llama.cpp)."""
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _roll() -> None:
    """Reset the counters when the UTC day changes. Caller holds the lock."""
    global _day, _neurons, _calls
    today = _today()
    if _day != today:
        _day = today
        _neurons = 0.0
        _calls = 0


def check() -> None:
    """Raise LLM_BUDGET_EXHAUSTED when today's allowance is spent.

    Checked *before* a call rather than after, so the service refuses politely
    instead of discovering the overrun from a provider error mid-stream.
    """
    limit = settings.llm_daily_neuron_budget
    with _lock:
        _roll()
        if limit > 0 and _neurons >= limit:
            raise errors.LLM_BUDGET_EXHAUSTED(
                detail=f"{_neurons:.0f}/{limit} neurons used today",
                retry_after=_seconds_to_reset(),
            )
        call_cap = settings.llm_daily_call_cap
        if call_cap > 0 and _calls >= call_cap:
            raise errors.LLM_BUDGET_EXHAUSTED(
                detail=f"{_calls}/{call_cap} provider calls used today",
                retry_after=_seconds_to_reset(),
            )


def record(prompt_tokens: int, completion_tokens: int,
           reported_neurons: float | None = None) -> None:
    """Record one provider call's usage. Called from llm.py on success.

    Reporting at the call site rather than at the answer site is the point: it
    counts the condense call, any future tool call, and anything else that
    reaches the provider, without each new caller having to remember to.

    `reported_neurons` is Cloudflare's own figure from the usage block, and it
    wins when present. The local formula was checked against it on 2026-08-20
    and reproduces it to eight decimal places (24 prompt / 109 completion
    tokens -> 3.19090909 computed, 3.19090915 reported), so this is not a
    correction — it is insurance against a pricing change silently making the
    constants wrong, which is the kind of drift a budget cannot afford.
    """
    global _neurons, _calls
    with _lock:
        _roll()
        if reported_neurons is not None and reported_neurons >= 0:
            _neurons += float(reported_neurons)
        else:
            _neurons += neurons_for(prompt_tokens, completion_tokens)
        _calls += 1


def record_estimated(prompt_text: str, completion_text: str) -> None:
    """Record a call whose provider returned no usage block."""
    record(estimate_tokens(prompt_text), estimate_tokens(completion_text))


def snapshot() -> dict:
    with _lock:
        _roll()
        limit = settings.llm_daily_neuron_budget
        return {
            "day": _day,
            "neurons_used": round(_neurons, 1),
            "neurons_limit": limit,
            "neurons_remaining": round(max(0.0, limit - _neurons), 1) if limit > 0 else None,
            "provider_calls": _calls,
            "call_cap": settings.llm_daily_call_cap or None,
            "enabled": limit > 0 or settings.llm_daily_call_cap > 0,
            "rates": {
                "neurons_per_m_input": settings.neurons_per_m_input,
                "neurons_per_m_output": settings.neurons_per_m_output,
            },
        }


def reset_for_tests() -> None:
    global _day, _neurons, _calls
    with _lock:
        _day = None
        _neurons = 0.0
        _calls = 0
