"""Redaction for anything that gets written down.

The chat log stored every question and answer verbatim, and students type things
like "my ID is 1191234, why is my registration blocked?". That text then sat in
a JSONL file, was rendered in the admin console, and would have been shipped
inside the deployed image. None of that is necessary to operate the service.

Two layers:

  * `text()` masks identifiers wherever they appear — student/national ids,
    emails, phone numbers, and anything that looks like a credential or token.
    Applied before writing, so the raw value never reaches disk.
  * The `aggregate` log mode (config.chat_log_mode) doesn't store question or
    answer text at all — only what operations actually needs: verdicts, timings,
    error codes, source ids. Raw text requires an explicit opt-in and a stated
    retention period.

Masks preserve shape (`[id:7]`, `[email]`) so a log line still reads sensibly
and so two occurrences of the same kind of thing remain distinguishable from one
occurrence — without the value.
"""

from __future__ import annotations

import re

# Order matters: emails before phone/id patterns, or the digits inside an
# address get masked first and the address stops matching.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    # Bearer/API-key shapes. Before the digit rules so a token with digits in it
    # is masked as a secret rather than partially masked as an id.
    (re.compile(r"\b(?:hf|gsk|sk|xox[abprs])[-_][A-Za-z0-9_-]{16,}\b"), "[token]"),
    (re.compile(r"(?i)\b(bearer|authorization)\s+\S+"), r"\1 [token]"),
    (re.compile(r"(?i)\b(pass(?:word|wd)?|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
     r"\1=[redacted]"),
    # Phone numbers, including the +970 / 00970 forms students write.
    (re.compile(r"(?:\+|00)\d[\d\s()-]{7,}\d"), "[phone]"),
    # Bare identifier runs: Birzeit student ids and Palestinian national ids.
    (re.compile(r"(?<![\d.])\d{7,9}(?![\d.])"), "[id]"),
    # Long card-like digit runs.
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card]"),
]


def text(value: str | None, limit: int = 2000) -> str | None:
    """Mask identifiers in free text. None stays None."""
    if not value:
        return value
    out = value[:limit]
    for pattern, replacement in _RULES:
        out = pattern.sub(replacement, out)
    return out


def ip(address: str | None) -> str | None:
    """Coarsen an IP so a log can show locality without identifying a device.

    IPv4 keeps two octets, IPv6 keeps the routing prefix. Enough to tell
    "on campus" from "somewhere else" and to spot one source hammering the API;
    not enough to point at a person.
    """
    if not address:
        return None
    if ":" in address:
        parts = address.split(":")
        return ":".join(parts[:3]) + "::/48"
    parts = address.split(".")
    if len(parts) == 4:
        return ".".join(parts[:2]) + ".x.x"
    return "?"


def headers(raw: dict) -> dict:
    """Strip credentials from headers before they are logged."""
    drop = {"authorization", "cookie", "set-cookie", "x-admin-token", "proxy-authorization"}
    return {
        k: ("[redacted]" if k.lower() in drop else v)
        for k, v in raw.items()
    }
