#!/usr/bin/env python3
"""CI gate: the disclosures match the code, and match each other.

Two privacy documents exist — the served page (`src/ritaj/static/privacy.html`)
and the store submission copy (`chrome-extension/store/privacy-policy.md`) — and
they drifted from reality on three separate points at once:

  * they named **Groq** as the model host after the provider had changed;
  * they said **no names are collected** while the web portal gated every chat
    behind a name field and sent it to the backend with each message;
  * the store listing said **independent student project** while the generation
    system prompt introduced the assistant as the *official* Birzeit helper.

A privacy policy that is checked only by reading is a privacy policy that drifts.
These assertions are derived from the code and configuration wherever possible,
so a future change to either has to update the disclosure to stay green.

Usage: python scripts/check_privacy.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

HTML = ROOT / "src" / "ritaj" / "static" / "privacy.html"
MARKDOWN = ROOT / "chrome-extension" / "store" / "privacy-policy.md"
SUBMISSION = ROOT / "chrome-extension" / "store" / "SUBMISSION.md"
MANIFEST = ROOT / "chrome-extension" / "manifest.json"
PORTAL_SRC = ROOT / "ritaj-student-portal" / "src"

# Claims that were true of an earlier build and are false now, or that cannot be
# supported at all.
FORBIDDEN = [
    (re.compile(r"\bGroq\b"), "names Groq as the model host",
     # The provider-change note is allowed to mention it by name.
     re.compile(r"(?i)earlier version of this policy named groq|كانت نسخة سابقة")),
    (re.compile(r"(?i)\bprivacy[- ]complete\b"), "claims 'privacy complete'", None),
    (re.compile(r"(?i)\bnothing is (?:collected|stored)\b"),
     "claims nothing is collected", None),
    (re.compile(r"(?i)\bcompletely (?:private|anonymous)\b"),
     "claims complete privacy/anonymity", None),
    (re.compile(r"(?i)\b(?:we are|this is) an official\b"),
     "claims to be official", None),
    (re.compile(r"(?i)\bguarantee[sd]?\b.{0,30}\b(accurate|correct|up.to.date)\b"),
     "guarantees accuracy", None),
]

# Every document must positively state these.
REQUIRED = [
    (re.compile(r"(?i)\bindependent\b"), "states the project is independent"),
    (re.compile(r"(?i)cloudflare"), "names the actual model host"),
    (re.compile(r"(?i)limited use"), "carries the Chrome Limited Use statement"),
    (re.compile(r"(?i)\bsidePanel\b"), "lists the sidePanel permission"),
    (re.compile(r"(?i)30 ?(days|يوم)"), "states the retention period"),
]


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def check_document(path: Path) -> int:
    # A comment is not a disclosure — a student never reads it. Stripping them
    # also lets the source explain *why* a claim is forbidden without tripping
    # the check that forbids it.
    text = _HTML_COMMENT.sub("", path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT)
    errors = 0
    for pattern, why, exemption in FORBIDDEN:
        for match in pattern.finditer(text):
            window = text[max(0, match.start() - 200): match.end() + 200]
            if exemption and exemption.search(window):
                continue
            line = text[: match.start()].count("\n") + 1
            print(f"  ERROR {rel}:{line} {why}")
            errors += 1
    for pattern, why in REQUIRED:
        if not pattern.search(text):
            print(f"  ERROR {rel} does not state: {why}")
            errors += 1
    if not errors:
        print(f"  {rel} OK")
    return errors


def check_matches_manifest() -> int:
    """Permissions in the manifest must be the ones the policy discloses."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    permissions = set(manifest.get("permissions", []))
    hosts = manifest.get("host_permissions", [])
    errors = 0

    for path in (HTML, MARKDOWN):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for permission in permissions:
            if permission not in text:
                print(f"  ERROR {rel} does not disclose the {permission!r} permission")
                errors += 1
        for host in hosts:
            hostname = urlparse(host.replace("*", "")).hostname or host.strip("*/")
            if hostname and hostname not in text:
                print(f"  ERROR {rel} does not disclose backend host {hostname}")
                errors += 1
    if not errors:
        print("  disclosed permissions match the manifest")
    return errors


def check_portal_collects_no_name() -> int:
    """The name gate is gone and the portal sends no `user` field."""
    errors = 0
    if not PORTAL_SRC.is_dir():
        print("  note: portal source not present; skipped")
        return 0
    for path in PORTAL_SRC.rglob("*.ts*"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        if "NameGate" in text and "removed" not in text:
            print(f"  ERROR {rel} still renders a name gate")
            errors += 1
        if re.search(r"\buser:\s*(meta\.user|userName)", text):
            print(f"  ERROR {rel} still sends a name to the backend")
            errors += 1
    if not errors:
        print("  portal collects no name")
    return errors


def check_identity_is_consistent() -> int:
    """The system prompt and the store listing must agree on what this is."""
    from ritaj.generate import SYSTEM_PROMPT

    errors = 0
    lowered = SYSTEM_PROMPT.lower()
    if "independent" not in lowered:
        print("  ERROR the generation system prompt does not say the assistant "
              "is independent")
        errors += 1
    if re.search(r"the official birzeit", lowered):
        print("  ERROR the generation system prompt claims to be official")
        errors += 1
    if SUBMISSION.exists():
        listing = SUBMISSION.read_text(encoding="utf-8")
        if "independent" not in listing.lower():
            print("  ERROR the store listing does not say the project is independent")
            errors += 1
    if not errors:
        print("  system prompt and store listing agree: independent")
    return errors


def main() -> None:
    print("Privacy disclosure consistency\n")
    errors = check_document(HTML)
    errors += check_document(MARKDOWN)
    print("\nPermissions vs. manifest\n")
    errors += check_matches_manifest()
    print("\nPortal data collection\n")
    errors += check_portal_collects_no_name()
    print("\nProduct identity\n")
    errors += check_identity_is_consistent()

    print()
    if errors:
        sys.exit(f"FAILED: {errors} disclosure problem(s).")
    print("OK — disclosures match the code.")


if __name__ == "__main__":
    main()
