"""LLM client — one thin wrapper over the OpenAI-compatible chat API.

Ollama (dev), Cloudflare Workers AI (pilot: `@cf/google/gemma-4-26b-a4b-it`) and
a self-hosted vLLM/llama.cpp server all speak this exact protocol, so this code
is identical for all of them; only LLM_BASE_URL / LLM_MODEL / LLM_API_KEY change.

Failure handling (roadmap Phase 1, task 7). A hosted free tier fails in ways a
localhost Ollama never did — throttling, cold model swaps, transient 5xx — so:

  * **bounded timeouts** split connect from read, because a hung connect should
    fail in seconds while a legitimately slow generation gets its full budget;
  * **one retry with jitter** for transient failures only (timeouts, connection
    errors, 429/5xx). Retrying a 400 just burns quota twice;
  * **a circuit breaker**, so when the provider is down we stop sending it
    traffic (and stop making every student wait out the timeout) until a cooling
    period passes;
  * **streams are never retried once a token has been emitted** — the client has
    already rendered that text, and a retry would duplicate or contradict it.

Every failure leaves as a `PublicError`: the student sees a stable code, the
operator sees the provider's actual message in the protected log.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections.abc import Iterator

import httpx

from . import budget, errors, runtime_config
from .config import settings

log = logging.getLogger("ritaj.llm")

# Connect fast or fail; allow a long read for generation. The read budget is the
# whole-answer ceiling, so it must exceed the slowest acceptable full answer
# (Phase 7 SLO: p95 <= 12 s) with headroom for a cold provider.
_TIMEOUT = httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)

# Status codes worth trying once more: rate limiting and server-side faults.
_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class _CircuitBreaker:
    """Stop hammering a provider that is clearly down.

    After `threshold` consecutive failures the circuit opens and every call
    fails immediately with LLM_UNAVAILABLE for `cooldown` seconds. One success
    closes it again. This is deliberately simple — a half-open state with
    probabilistic admission buys little at this traffic level and is harder to
    reason about during an incident.
    """

    def __init__(self, threshold: int = 5, cooldown: float = 30.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None

    def check(self) -> None:
        with self._lock:
            if self._opened_at is None:
                return
            if time.monotonic() - self._opened_at < self.cooldown:
                remaining = self.cooldown - (time.monotonic() - self._opened_at)
                raise errors.LLM_UNAVAILABLE(
                    detail=f"circuit open, {remaining:.0f}s remaining",
                    retry_after=max(1, int(remaining)),
                )
            # Cooldown elapsed — let the next call through to probe the provider.
            self._opened_at = None
            self._failures = 0

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold and self._opened_at is None:
                self._opened_at = time.monotonic()
                log.error("LLM circuit opened after %d consecutive failures", self._failures)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "open": self._opened_at is not None,
                "consecutive_failures": self._failures,
            }


_breaker = _CircuitBreaker()


def circuit_state() -> dict:
    """Breaker status for /ready and the admin console."""
    return _breaker.snapshot()


def _payload(messages: list[dict], temperature: float, max_tokens: int, stream: bool) -> dict:
    # llm_model is tunable from /admin; blank falls back to the .env default.
    return {
        "model": runtime_config.get("llm_model") or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def _defaults(temperature: float | None, max_tokens: int | None) -> tuple[float, int]:
    if temperature is None:
        temperature = runtime_config.get("temperature")
    if max_tokens is None:
        max_tokens = runtime_config.get("max_tokens")
    return temperature, max_tokens


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }


def _url() -> str:
    return f"{settings.llm_base_url.rstrip('/')}/chat/completions"


def _classify(exc: Exception) -> tuple[bool, Exception]:
    """(is_transient, public_error) for an exception raised against the provider."""
    if isinstance(exc, httpx.TimeoutException):
        return True, errors.LLM_TIMEOUT(detail=repr(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        # Provider bodies can echo the prompt; keep only a short prefix, and only
        # in the private detail field.
        body = exc.response.text[:200] if exc.response.content else ""
        transient = status in _RETRYABLE_STATUS
        return transient, errors.LLM_UNAVAILABLE(detail=f"HTTP {status}: {body}")
    if isinstance(exc, httpx.HTTPError):
        return True, errors.LLM_UNAVAILABLE(detail=repr(exc))
    return False, errors.LLM_UNAVAILABLE(detail=repr(exc))


def _sleep_before_retry(attempt: int) -> None:
    """Short backoff with jitter — spread retries so a recovering provider isn't
    hit by every waiting request at the same instant."""
    time.sleep(0.4 * attempt + random.uniform(0, 0.3))


def _meter(usage: dict | None, messages: list[dict], produced: str) -> None:
    """Record what this call cost against the daily budget.

    Metered here, at the only place that talks to the provider, so every caller
    is counted — including `generate.condense`, whose extra call the previous
    per-answer accounting missed entirely.

    Cloudflare returns a `usage` block; Ollama and llama.cpp do not, so those
    fall back to a character-based estimate. An estimate is far better than
    skipping the call: an unmetered path is how a budget quietly stops binding.
    """
    if usage:
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        # Cloudflare reports the exact neuron cost; pass it through so the daily
        # budget cannot drift from the provider's own accounting.
        reported = usage.get("neurons")
        if prompt_tokens or completion_tokens:
            budget.record(prompt_tokens, completion_tokens,
                          float(reported) if reported is not None else None)
            return
    prompt_text = "".join(str(m.get("content", "")) for m in messages)
    budget.record_estimated(prompt_text, produced)


def _require_answer(choice: dict, max_tokens: int) -> None:
    """Refuse to return an empty answer that the provider charged for.

    `@cf/google/gemma-4-26b-a4b-it` is a reasoning model: it emits
    `reasoning_content` before `content`, and those tokens bill as output. On a
    measured RAG-shaped call, reasoning was about 70% of the output (200 of 285
    tokens). So a `max_tokens` that looks generous for an answer can be spent
    entirely on thinking, and the provider then returns 200 OK with
    `content: ""` — a silently empty answer that the grounding checks downstream
    would treat as an ungrounded response rather than as a configuration fault.

    Verified 2026-08-20: max_tokens=60 on a trivial prompt returned 60
    completion tokens and empty content.
    """
    message = choice.get("message") or {}
    if (message.get("content") or "").strip():
        return
    reasoning = (message.get("reasoning_content") or "").strip()
    if reasoning and choice.get("finish_reason") == "length":
        raise errors.LLM_UNAVAILABLE(
            detail=(f"model spent its entire {max_tokens}-token output budget on "
                    "reasoning and returned no answer — raise max_tokens")
        )
    raise errors.LLM_UNAVAILABLE(detail="provider returned an empty answer")


def chat(messages: list[dict], temperature: float | None = None,
         max_tokens: int | None = None) -> str:
    """Send a chat completion request and return the assistant's text.

    Retried at most once on a transient failure. Non-streamed, so a retry is
    safe: nothing has been shown to the student yet.
    """
    temperature, max_tokens = _defaults(temperature, max_tokens)
    _breaker.check()
    payload = _payload(messages, temperature, max_tokens, stream=False)

    last: Exception | None = None
    for attempt in (1, 2):
        try:
            resp = httpx.post(_url(), headers=_headers(), json=payload, timeout=_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            _breaker.record_success()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            # Meter FIRST: the call cost neurons whether or not it produced an
            # answer, and an unbilled failure is how a budget stops binding.
            _meter(body.get("usage"), messages, content or "")
            _require_answer(choice, max_tokens)
            return content
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            transient, public = _classify(exc)
            _breaker.record_failure()
            last = public
            log.warning("LLM call failed (attempt %d/%d): %s", attempt, 2, public)
            if not transient or attempt == 2:
                break
            _sleep_before_retry(attempt)
    raise last if last else errors.LLM_UNAVAILABLE(detail="unknown failure")


def chat_stream(
    messages: list[dict], temperature: float | None = None,
    max_tokens: int | None = None
) -> Iterator[str]:
    """Stream a chat completion, yielding text deltas as the model produces them.

    OpenAI-compatible SSE: lines of `data: {json}` each carrying an incremental
    `choices[0].delta.content`, terminated by `data: [DONE]`.

    The retry is only attempted while `emitted` is still False. Once the caller
    has seen a delta it has been streamed onward to the browser and rendered;
    restarting would replay or contradict visible text, which is worse than the
    error the student would otherwise get.
    """
    temperature, max_tokens = _defaults(temperature, max_tokens)
    _breaker.check()
    payload = _payload(messages, temperature, max_tokens, stream=True)

    emitted = False
    last: Exception | None = None
    for attempt in (1, 2):
        produced: list[str] = []
        usage: dict | None = None
        try:
            with httpx.stream("POST", _url(), headers=_headers(), json=payload,
                              timeout=_TIMEOUT) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    # Cloudflare attaches usage to the final chunk, alongside a
                    # delta that carries no content — so it has to be read before
                    # the content check below skips the chunk.
                    if isinstance(chunk.get("usage"), dict):
                        usage = chunk["usage"]
                    try:
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError):
                        continue
                    if delta:
                        emitted = True
                        produced.append(delta)
                        yield delta
            _breaker.record_success()
            _meter(usage, messages, "".join(produced))
            return
        except (httpx.HTTPError, ValueError) as exc:
            transient, public = _classify(exc)
            _breaker.record_failure()
            last = public
            log.warning("LLM stream failed (attempt %d, emitted=%s): %s",
                        attempt, emitted, public)
            if emitted or not transient or attempt == 2:
                break
            _sleep_before_retry(attempt)
    raise last if last else errors.LLM_UNAVAILABLE(detail="unknown stream failure")
