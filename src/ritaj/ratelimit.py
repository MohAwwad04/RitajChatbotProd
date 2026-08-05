"""Anonymous rate limiting and a global generation cap.

The public chat endpoint had neither. One client could exhaust a day's LLM quota
in a couple of minutes, and unbounded concurrency on a 2-vCPU host means every
student's answer gets slower while the free allowance drains.

## Two independent buckets, not one combined key

The first implementation hashed *IP + session_id together*. That reads as
"defence in depth" and is the opposite: the session id is chosen by the client,
so minting a fresh one produced a fresh bucket and an unlimited number of
provider calls. A limit an attacker can reset is not a limit.

So the two signals are now separate limiters, and a request must satisfy both:

  * **Network bucket** — keyed on the client address alone. The client cannot
    change this, so it is the limit that actually holds. Its allowances are
    higher, because a campus NAT puts many honest students behind one address.
  * **Session bucket** — keyed on the client-supplied session id alone. Tighter,
    and trivially reset by a hostile client, which is fine: its job is to stop a
    *single conversation* from running away, not to stop abuse.

Neither is a substitute for the daily provider budget (`budget.py`), which is
the backstop that survives both being wrong.

## Whose address is it?

Behind a hosting proxy, `request.client.host` is the *proxy*, not the student —
so every user lands in one network bucket and the limit becomes global. But
`X-Forwarded-For` is a client-settable header: trusting it unconditionally hands
the attacker the bucket key again.

The resolution is explicit configuration, not a heuristic. `TRUSTED_PROXY_COUNT`
says how many proxies sit in front of this deployment; the client address is
taken that many hops from the right of the forwarded chain. Default 0 means the
header is ignored entirely — safe against spoofing, and the failure mode is a
global limit rather than a bypass. `client_ip_diagnostics()` surfaces the
misconfiguration on /ready so an operator can see which one they have.

## Scope

Both limiters are in-process. With one worker — which is what this deployment
runs (`scripts/start.sh --workers 1`) — that is exact. **Horizontal scaling
requires shared state**: with N replicas the effective limits become N times
what is configured. Raise the replica count only after moving these counters to
a shared store; do not compensate by lowering the numbers, which would penalise
honest students to contain an attacker.
"""

from __future__ import annotations

import ipaddress
import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from . import errors
from .config import settings

log = logging.getLogger("ritaj.ratelimit")

# Rotated daily so a bucket key cannot be correlated across days, and chosen at
# random per process so it is not guessable from outside (an attacker who knew
# the salt could confirm whether a specific address had used the service).
_salt_lock = threading.Lock()
_salt = secrets.token_bytes(16)
_salt_day: int | None = None


def _current_salt() -> bytes:
    global _salt, _salt_day
    day = int(time.time() // 86400)
    with _salt_lock:
        if _salt_day != day:
            _salt = secrets.token_bytes(16)
            _salt_day = day
        return _salt


def _hash(label: str, value: str) -> str:
    digest = hashlib.sha256()
    digest.update(_current_salt())
    digest.update(label.encode())
    digest.update(b"\x00")
    digest.update(value.encode())
    return digest.hexdigest()[:16]


def network_key(ip: str | None) -> str:
    """Bucket key for a client address. Never reversible to the address."""
    return _hash("net", ip or "?")


def session_key(session_id: str | None) -> str:
    """Bucket key for a client-supplied session id.

    A missing or blank id collapses to one shared bucket on purpose: a client
    that declines to identify its conversation gets the limit that a single
    conversation would have, rather than an exemption.
    """
    return _hash("sess", (session_id or "").strip() or "anonymous")


def client_ip(request) -> str | None:
    """The address to rate-limit on, honouring only a configured proxy chain.

    `TRUSTED_PROXY_COUNT` is the number of proxies this deployment sits behind.
    With n trusted proxies, the client is the n-th entry from the right of
    `X-Forwarded-For`; everything further right was appended by infrastructure we
    control, and everything further left can be forged by the client.
    """
    peer = request.client.host if request.client else None
    hops = settings.trusted_proxy_count
    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not chain:
        return peer
    # chain[-1] is the address seen by the closest trusted proxy. With n trusted
    # proxies the originating client is n entries from the right.
    index = len(chain) - hops
    if index < 0:
        # Fewer hops than configured: the chain is shorter than expected, so the
        # leftmost entry is the best available answer and is still client-forgeable.
        # Prefer the peer over trusting a short chain.
        log.warning("X-Forwarded-For has %d hop(s), fewer than TRUSTED_PROXY_COUNT=%d",
                    len(chain), hops)
        return peer
    candidate = chain[index]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        log.warning("X-Forwarded-For entry is not an IP address; falling back to peer")
        return peer
    return candidate


def _is_private(address: str | None) -> bool:
    if not address:
        return False
    try:
        return ipaddress.ip_address(address).is_private
    except ValueError:
        return False


def client_ip_diagnostics(request) -> dict:
    """Whether the address used for limiting is plausibly the real client.

    Reported on /ready because the failure is silent and expensive both ways: a
    private peer with no trusted-proxy configuration means every student shares
    one bucket, and a trusted-proxy count that is too high means the client can
    choose its own.
    """
    peer = request.client.host if request.client else None
    has_forwarded = bool(request.headers.get("x-forwarded-for"))
    hops = settings.trusted_proxy_count
    if hops <= 0 and _is_private(peer) and has_forwarded:
        return {
            "ok": False,
            "reason": "behind a proxy with TRUSTED_PROXY_COUNT=0 — the network "
                      "rate limit is effectively global",
        }
    if hops > 0 and not has_forwarded:
        return {
            "ok": False,
            "reason": f"TRUSTED_PROXY_COUNT={hops} but no X-Forwarded-For header "
                      "was present",
        }
    return {"ok": True, "reason": None}


@dataclass(frozen=True)
class Window:
    seconds: int
    limit: int
    name: str


class SlidingWindowLimiter:
    """Per-key sliding windows over request timestamps.

    Sliding rather than fixed windows: with a fixed window a client can spend
    the whole minute's allowance at 0:59 and the next at 1:01, producing double
    the intended burst exactly when the service is least able to absorb it.
    """

    def __init__(self, windows: list[Window]):
        self.windows = sorted(windows, key=lambda w: w.seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """Drop keys with no recent activity so memory can't grow unbounded."""
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        longest = self.windows[-1].seconds if self.windows else 0
        for key in [k for k, hits in self._hits.items()
                    if not hits or now - hits[-1] > longest]:
            del self._hits[key]

    def check(self, key: str, *, record: bool = True) -> tuple[bool, int, str]:
        """(allowed, retry_after_seconds, window_name).

        `record=False` tests the limit without consuming an allowance, so a
        request refused by a *later* limiter does not also burn this one — a
        blocked request should not cost the caller twice.
        """
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            hits = self._hits[key]
            longest = self.windows[-1].seconds if self.windows else 0
            while hits and now - hits[0] > longest:
                hits.popleft()

            for window in self.windows:
                cutoff = now - window.seconds
                count = sum(1 for t in hits if t > cutoff)
                if count >= window.limit:
                    oldest = next(t for t in hits if t > cutoff)
                    retry = max(1, int(window.seconds - (now - oldest)) + 1)
                    return False, retry, window.name

            if record:
                hits.append(now)
            return True, 0, ""

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _network_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter([
        Window(60, settings.network_rate_limit_per_minute, "network-per-minute"),
        Window(3600, settings.network_rate_limit_per_hour, "network-per-hour"),
        Window(86400, settings.network_rate_limit_per_day, "network-per-day"),
    ])


def _session_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter([
        Window(60, settings.rate_limit_per_minute, "session-per-minute"),
        Window(3600, settings.rate_limit_per_hour, "session-per-hour"),
        Window(86400, settings.rate_limit_per_day, "session-per-day"),
    ])


_network = _network_limiter()
_session = _session_limiter()


def check(ip: str | None, session_id: str | None) -> None:
    """Raise RATE_LIMITED unless BOTH buckets have allowance.

    The network bucket is checked first and is the one that actually constrains
    an attacker; the session bucket is a courtesy limit on a single conversation.
    Both are probed before either records, so a request rejected by the second
    limiter has not consumed the first's allowance.
    """
    net_ok, net_retry, net_window = _network.check(network_key(ip), record=False)
    if not net_ok:
        raise errors.RATE_LIMITED(
            detail=f"{net_window} limit reached", retry_after=net_retry
        )

    sess_ok, sess_retry, sess_window = _session.check(session_key(session_id), record=False)
    if not sess_ok:
        raise errors.RATE_LIMITED(
            detail=f"{sess_window} limit reached", retry_after=sess_retry
        )

    _network.check(network_key(ip))
    _session.check(session_key(session_id))


def reset_for_tests() -> None:
    """Rebuild every limiter AND the concurrency cap from the current settings.

    The cap is constructed at import, so a test that changes
    `max_concurrent_generations` or `queue_timeout_seconds` without rebuilding it
    silently measures the old values — which is how a load test can report that
    a queue timeout never fires when the timeout it set was never in effect.
    """
    global _network, _session, _cap
    _network = _network_limiter()
    _session = _session_limiter()
    _cap = ConcurrencyCap(settings.max_concurrent_generations,
                          settings.queue_timeout_seconds)


class ConcurrencyCap:
    """Bounded simultaneous generations, with a short queue then a clear refusal.

    Queuing forever is the wrong behaviour on a metered provider: the client has
    already given up and reconnected, but the server is still holding a slot and
    paying for tokens nobody will read.
    """

    def __init__(self, limit: int, timeout: float):
        self._sem = threading.BoundedSemaphore(max(1, limit))
        self._timeout = timeout
        self._active = 0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Take a slot, or raise BUSY.

        Exposed separately from the context manager because the streaming route
        has to acquire *before* it returns a StreamingResponse and release when
        the generator finishes — a `with` block cannot span that boundary, and
        acquiring inside the generator would surface BUSY as a mid-stream error
        event after the client had already been sent the sources.
        """
        if not self._sem.acquire(timeout=self._timeout):
            raise errors.BUSY(
                detail=f"no generation slot within {self._timeout}s",
                retry_after=max(1, int(self._timeout)),
            )
        with self._lock:
            self._active += 1

    def release(self) -> None:
        """Give the slot back. Exactly one release per acquire.

        No "already released?" guard here on purpose: a shared counter cannot
        tell whose release is the duplicate, so a guard would silently absorb
        one caller's bug into another caller's slot. BoundedSemaphore raises on
        over-release instead, which is the failure being loud rather than
        leaking capacity.
        """
        with self._lock:
            self._active -= 1
        self._sem.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    @property
    def active(self) -> int:
        with self._lock:
            return self._active


_cap = ConcurrencyCap(settings.max_concurrent_generations, settings.queue_timeout_seconds)


def generation_slot() -> ConcurrencyCap:
    """Context manager for one generation. Raises BUSY when the host is full."""
    return _cap


def snapshot() -> dict:
    """Live counters for /ready and the admin console."""
    return {
        "active_generations": _cap.active,
        "max_concurrent": settings.max_concurrent_generations,
        "trusted_proxy_count": settings.trusted_proxy_count,
        "session_limits": {
            "per_minute": settings.rate_limit_per_minute,
            "per_hour": settings.rate_limit_per_hour,
            "per_day": settings.rate_limit_per_day,
        },
        "network_limits": {
            "per_minute": settings.network_rate_limit_per_minute,
            "per_hour": settings.network_rate_limit_per_hour,
            "per_day": settings.network_rate_limit_per_day,
        },
        # Single-process counters. See this module's docstring before scaling out.
        "scope": "in-process (valid for a single worker / single replica)",
    }
