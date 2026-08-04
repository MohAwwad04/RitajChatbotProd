"""Interaction telemetry — aggregate by default, raw text only on opt-in.

This log used to store every question and answer verbatim, forever, with no
retention limit and no redaction, and rendered it in the admin console. Students
type identifiers into chat ("my ID is 1191234, why is my registration blocked?"),
so that file accumulated personal data the service has no reason to keep.

Two modes (`CHAT_LOG_MODE`):

  * **aggregate** (default) — what operating the service actually needs:
    verdicts, block categories, latencies, source ids, error codes, client and
    language. No question text, no answer text.
  * **full** — question and answer text as well, redacted, and only with an
    explicit opt-in plus a stated retention period. Intended for a supervised
    pilot with informed participants, not for general availability.

Both modes redact before writing and enforce `CHAT_LOG_RETENTION_DAYS` on read
and on append, so an old entry stops being visible and then stops existing —
rather than "we intend to delete it" living in a policy document.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import redact
from .config import settings

_PATH = Path(settings.chat_log_path)
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expired(entry: dict, cutoff: datetime) -> bool:
    stamp = entry.get("ts")
    if not stamp:
        return False
    try:
        return datetime.fromisoformat(stamp) < cutoff
    except ValueError:
        return False


def record(
    question: str,
    answer: str,
    *,
    verdict: str | None = None,
    repaired: bool = False,
    blocked: str | None = None,
    injection: bool = False,
    user: str | None = None,
    session: str | None = None,
    client: str | None = None,
    request_id: str | None = None,
    sources: list[str] | None = None,
    latency_ms: float | None = None,
    error_code: str | None = None,
) -> None:
    """Append one interaction (best-effort; never raises)."""
    entry = {
        "ts": _now().isoformat(timespec="seconds"),
        "request_id": request_id,
        # A session id groups one conversation's turns. It is client-generated
        # and random, so it identifies a chat, not a student.
        "session": session,
        "client": client,
        "verdict": verdict,
        "repaired": repaired,
        "blocked": blocked,
        "injection": injection,
        "error_code": error_code,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        # Which approved documents were used — the operational question ("is the
        # corpus answering?") without the student's words.
        "sources": sources or [],
        "question_chars": len(question or ""),
        "answer_chars": len(answer or ""),
    }

    if settings.chat_log_mode == "full":
        entry["question"] = redact.text(question)
        entry["answer"] = redact.text(answer)
        # `user` is a self-reported display name. It only exists in full mode,
        # and the portal no longer asks for one (Phase 8).
        entry["user"] = redact.text(user)

    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        try:
            with _PATH.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def recent(limit: int = 200) -> list[dict]:
    """Most recent interactions, newest first, excluding expired entries."""
    if not _PATH.exists():
        return []
    try:
        lines = _PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    cutoff = _now() - timedelta(days=settings.chat_log_retention_days)
    out = []
    for raw in lines[-limit * 2:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if _expired(entry, cutoff):
            continue
        out.append(entry)
    out.reverse()
    return out[:limit]


def purge_expired() -> int:
    """Delete entries past the retention period. Returns how many were removed.

    Called on a schedule and after writes; retention that is only applied on
    read leaves the data on disk, which is the thing the policy promises not to
    do.
    """
    if not _PATH.exists():
        return 0
    cutoff = _now() - timedelta(days=settings.chat_log_retention_days)
    with _lock:
        try:
            lines = _PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        kept: list[str] = []
        removed = 0
        for raw in lines:
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except ValueError:
                removed += 1
                continue
            if _expired(entry, cutoff):
                removed += 1
                continue
            kept.append(raw)
        if removed:
            try:
                _PATH.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
            except OSError:
                return 0
        return removed


def summary(limit: int = 1000) -> dict:
    """Aggregate counters for the admin console — no per-interaction text."""
    entries = recent(limit)
    verdicts: dict[str, int] = {}
    blocked: dict[str, int] = {}
    latencies = []
    for entry in entries:
        verdicts[entry.get("verdict") or "none"] = verdicts.get(entry.get("verdict") or "none", 0) + 1
        if entry.get("blocked"):
            blocked[entry["blocked"]] = blocked.get(entry["blocked"], 0) + 1
        if entry.get("latency_ms"):
            latencies.append(entry["latency_ms"])
    latencies.sort()

    def pct(p: float) -> float | None:
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    return {
        "mode": settings.chat_log_mode,
        "retention_days": settings.chat_log_retention_days,
        "interactions": len(entries),
        "verdicts": verdicts,
        "blocked": blocked,
        "injection_flagged": sum(1 for e in entries if e.get("injection")),
        "repaired": sum(1 for e in entries if e.get("repaired")),
        "latency_p50_ms": pct(0.5),
        "latency_p95_ms": pct(0.95),
    }


def clear() -> None:
    with _lock:
        try:
            _PATH.unlink(missing_ok=True)
        except OSError:
            pass
