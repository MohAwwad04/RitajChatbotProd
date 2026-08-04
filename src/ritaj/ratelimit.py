"""Anonymous rate limiting and a global generation cap.

The public chat endpoint had neither. One client could exhaust a day's LLM quota
in a couple of minutes, and unbounded concurrency on a 2-vCPU host means every
student's answer gets slower while the free allowance drains.

Two independent limits, because they fail differently:

  * **Per-caller limits** (minute/hour/day) stop one client monopolising the
    service. Keyed on a *salted hash* of the client IP plus the client's own
    session id — never the raw address. The salt rotates daily, so the buckets
    cannot be used to follow a student across days, and there is nothing in
    memory that reverses to an IP.
  * **A global concurrency cap** matches generation to what the host can
    actually do. Requests wait briefly for a slot and then get a clear `BUSY`
    rather than piling up behind each other.

Both are in-process. With one worker (which is what this deployment runs — see
scripts/start.sh) that is exact. A multi-instance deployment would need shared
state; the limits would then be per instance, which is a real weakening and
should be fixed with a shared store rather than by raising the numbers.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from . import errors
from .config import settings

# Rotated daily so a bucket key cannot be correlated across days, and chosen at
# random per process so it is not guessable from the outside (an attacker who
# knew the salt could confirm whether a specific IP had used the service).
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


def bucket_key(ip: str | None, session_id: str | None) -> str:
    """A privacy-preserving identifier for one caller.

    Both signals are used: the session id alone is client-controlled (a script
    can mint a new one per request), and the IP alone lumps a whole campus NAT
    into one bucket. Combining them limits a determined single client by network
    while leaving ordinary students on shared egress unaffected by each other.
    """
    digest = hashlib.sha256()
    digest.update(_current_salt())
    digest.update((ip or "?").encode())
    digest.update(b"|")
    digest.update((session_id or "").encode())
    return digest.hexdigest()[:16]


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

    def check(self, key: str) -> tuple[bool, int, str]:
        """(allowed, retry_after_seconds, window_name). Records the hit if allowed."""
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

            hits.append(now)
            return True, 0, ""

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _default_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter([
        Window(60, settings.rate_limit_per_minute, "per-minute"),
        Window(3600, settings.rate_limit_per_hour, "per-hour"),
        Window(86400, settings.rate_limit_per_day, "per-day"),
    ])


_limiter = _default_limiter()


def check(ip: str | None, session_id: str | None) -> None:
    """Raise RATE_LIMITED when this caller has had its share."""
    allowed, retry_after, window = _limiter.check(bucket_key(ip, session_id))
    if not allowed:
        raise errors.RATE_LIMITED(
            detail=f"{window} limit reached for bucket", retry_after=retry_after
        )


def reset_for_tests() -> None:
    global _limiter
    _limiter = _default_limiter()


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

    def __enter__(self):
        if not self._sem.acquire(timeout=self._timeout):
            raise errors.BUSY(
                detail=f"no generation slot within {self._timeout}s",
                retry_after=max(1, int(self._timeout)),
            )
        with self._lock:
            self._active += 1
        return self

    def __exit__(self, *exc):
        with self._lock:
            self._active -= 1
        self._sem.release()
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
        "limits": {
            "per_minute": settings.rate_limit_per_minute,
            "per_hour": settings.rate_limit_per_hour,
            "per_day": settings.rate_limit_per_day,
        },
    }
