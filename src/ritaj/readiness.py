"""Service lifecycle: liveness, readiness and startup timings.

The production 503 this replaces had a specific cause: `scripts/start.sh` ran the
whole index build *before* exec'ing uvicorn, so nothing was listening on the port
until the embedder had loaded and every chunk had been embedded. Hugging Face
waits 30 minutes for a healthy port and then kills the deployment — the app never
got to say "I'm alive, just not ready yet".

So the two questions are separated, as they are in any orchestrated deployment:

  * **live**  — the process is up and the event loop is turning. Never touches a
    model, the vector store or the network. If this fails, restart the process.
  * **ready** — the corpus is loaded, retrieval returns something, and the LLM is
    configured. If this fails, keep the process but send no traffic.

Initialization runs on a background thread; chat answers `503 INITIALIZING`
until it finishes, which is a *bounded, meaningful* failure a client can retry
rather than an opaque dead port.

Timings are kept for the four moments the roadmap asks to measure (process
listen, index ready, first retrieval, first token) because "startup is slow" is
not actionable and "the embedder took 41s of a 47s boot" is.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Literal

log = logging.getLogger("ritaj.readiness")

State = Literal["starting", "initializing", "ready", "failed"]

_lock = threading.Lock()
_state: State = "starting"
_error: str | None = None
_detail: dict = {}
# Monotonic clock for durations; wall clock only for human-readable stamps.
_t0 = time.monotonic()
_timings: dict[str, float] = {}
_thread: threading.Thread | None = None


def _elapsed_ms() -> float:
    return round((time.monotonic() - _t0) * 1000, 1)


def mark(event: str) -> None:
    """Record milliseconds-since-process-start for a named startup milestone.

    First write wins: `first_retrieval` and `first_token` are meant to capture
    the *first* occurrence, and later requests must not overwrite them.
    """
    with _lock:
        if event not in _timings:
            _timings[event] = _elapsed_ms()
            log.info("startup: %s at %.1f ms", event, _timings[event])


def state() -> State:
    with _lock:
        return _state


def is_ready() -> bool:
    return state() == "ready"


def _set(new_state: State, *, error: str | None = None, **detail) -> None:
    global _state, _error
    with _lock:
        _state = new_state
        _error = error
        _detail.update(detail)
    if error:
        log.error("readiness -> %s: %s", new_state, error)
    else:
        log.info("readiness -> %s", new_state)


def snapshot() -> dict:
    """Everything /ready reports. Safe to expose: no paths, no secrets."""
    with _lock:
        return {
            "state": _state,
            "error": _error,
            "detail": dict(_detail),
            "timings_ms": dict(_timings),
            "uptime_ms": _elapsed_ms(),
        }


def start_background_init(initializer: Callable[[], dict]) -> None:
    """Run `initializer` on a daemon thread, tracking state around it.

    The callable returns a detail dict (chunk counts, corpus version, …) that is
    merged into the readiness snapshot. Any exception marks the service failed
    with the reason *type and message only* — this surface is public, so a stack
    trace with filesystem paths does not belong in it. The traceback goes to the
    protected log.

    Daemon thread: a stuck initializer must never prevent the process from
    exiting on shutdown.
    """
    global _thread

    def run() -> None:
        _set("initializing")
        started = time.monotonic()
        try:
            detail = initializer() or {}
        except Exception as exc:  # noqa: BLE001 — boundary: nothing above catches
            log.exception("initialization failed")
            _set("failed", error=f"{type(exc).__name__}: {exc}")
            return
        mark("index_ready")
        detail["init_seconds"] = round(time.monotonic() - started, 2)
        _set("ready", **detail)

    with _lock:
        if _thread is not None and _thread.is_alive():
            return  # already initializing; don't start a second builder
    _thread = threading.Thread(target=run, name="ritaj-init", daemon=True)
    _thread.start()


def wait_ready(timeout: float) -> bool:
    """Block until ready (or failed/timeout). For tests and CLI smoke checks."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state() in ("ready", "failed"):
            return state() == "ready"
        time.sleep(0.05)
    return False


def reset_for_tests() -> None:
    """Return the module to its pre-init state (tests only)."""
    global _state, _error, _thread, _t0
    with _lock:
        _state = "starting"
        _error = None
        _detail.clear()
        _timings.clear()
        _t0 = time.monotonic()
        _thread = None
