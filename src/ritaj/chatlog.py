"""Lightweight chat-interaction log (v1).

Appends every question/answer to chat_log.jsonl so the /admin "Log" tab can show
what users asked and how the assistant replied. Deliberately minimal — no DB, no
auth. The schema already leaves room for the planned next step (per-user names /
grouping by conversation): the `user` field is recorded as None for now.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

_PATH = Path(settings.chat_log_path)
_lock = threading.Lock()


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
) -> None:
    """Append one interaction to the log file (best-effort; never raises)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": user,            # self-reported display name from the client
        "session": session,      # groups the turns of one conversation
        "client": client,        # "portal" | "extension" | None (legacy)
        "question": question,
        "answer": answer,
        "verdict": verdict,
        "repaired": repaired,
        "blocked": blocked,
        "injection": injection,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        try:
            with _PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def recent(limit: int = 200) -> list[dict]:
    """Return the most recent interactions, newest first."""
    if not _PATH.exists():
        return []
    try:
        lines = _PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    out.reverse()
    return out


def clear() -> None:
    with _lock:
        try:
            _PATH.unlink(missing_ok=True)
        except OSError:
            pass
