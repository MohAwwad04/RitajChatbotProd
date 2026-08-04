"""Daily LLM budget — spend the free allowance deliberately, not by surprise.

Cloudflare's free Workers AI allocation is 10,000 neurons/day. At roughly 50
neurons for a representative RAG request (4,000 input + 500 output tokens) that
is about 200 answers before the provider starts refusing. A provider refusal
arrives as an opaque error mid-stream; an application budget that trips *below*
the provider's ceiling arrives as a sentence a student can understand, with the
Ritaj page still linked.

The budget counts answers, not neurons, because neuron accounting is per-model
and per-token and this service cannot see it from the response. Answers are the
unit that maps to student-visible behaviour, and the conversion is documented in
ADR-001 so the number can be re-derived if the price table changes.

Counting is in-process and resets at UTC midnight. Restarts lose the count,
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
_used = 0


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_to_reset() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow.timestamp() + 86400) - now.timestamp())


def check() -> None:
    """Raise LLM_BUDGET_EXHAUSTED when today's allowance is spent."""
    limit = settings.llm_daily_budget
    if limit <= 0:  # 0 disables the guard (development)
        return
    with _lock:
        _roll()
        if _used >= limit:
            raise errors.LLM_BUDGET_EXHAUSTED(
                detail=f"{_used}/{limit} answers used today",
                retry_after=_seconds_to_reset(),
            )


def _roll() -> None:
    """Reset the counter when the UTC day changes. Caller holds the lock."""
    global _day, _used
    today = _today()
    if _day != today:
        _day = today
        _used = 0


def consume(n: int = 1) -> None:
    """Record answers actually generated. Call after a successful LLM call."""
    global _used
    with _lock:
        _roll()
        _used += n


def snapshot() -> dict:
    with _lock:
        _roll()
        limit = settings.llm_daily_budget
        return {
            "day": _day,
            "used": _used,
            "limit": limit,
            "remaining": max(0, limit - _used) if limit > 0 else None,
            "enabled": limit > 0,
        }


def reset_for_tests() -> None:
    global _day, _used
    with _lock:
        _day = None
        _used = 0
