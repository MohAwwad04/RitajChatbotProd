#!/usr/bin/env python3
"""Inventory the deployment's secrets — names and status only, never values.

Roadmap Phase 0, task 5. Two jobs:

  1. Report which secrets each environment needs and whether one is configured,
     printing only presence + a fingerprint (first 8 hex of sha256). A
     fingerprint lets you confirm "staging and production hold the same token"
     or "this token changed after rotation" without ever displaying it.
  2. Scan the tracked repo for material that should never have been committed
     (private keys, provider tokens, plaintext password lists) so rotation
     decisions rest on evidence rather than memory.

Usage:
    python scripts/secret_inventory.py            # inventory + repo scan
    python scripts/secret_inventory.py --scan-only
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# name -> (where it must be set, why it matters, required-in-production?)
SECRETS: list[tuple[str, str, str, bool]] = [
    ("LLM_API_KEY", "app host secret",
     "Cloudflare Workers AI token — bills the account's neuron quota", True),
    ("HF_TOKEN", "operator's shell only",
     "Write access to the Space; can redeploy arbitrary code", False),
    ("ADMIN_USERS", "app host secret",
     "username:bcrypt pairs for /admin (hashes only, never plaintext)", True),
    ("SESSION_SECRET", "app host secret",
     "signs admin session tokens; weak value = forgeable admin session", True),
    ("ADMIN_TOKEN", "app host secret (legacy)",
     "single shared admin token; prefer ADMIN_USERS", False),
    ("CF_ACCOUNT_ID", "app host secret",
     "embedded in LLM_BASE_URL; identifies the billing account", False),
]

# Patterns for things that must never appear in tracked files. Deliberately
# specific — a scan that cries wolf gets ignored, and an ignored scan is worse
# than no scan.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    # Only a quoted *literal* counts. `const password = document.getElementById(…)`
    # reads a value, it doesn't embed one, and flagging it teaches operators to
    # ignore this scan.
    ("hardcoded password literal",
     re.compile(r"(?i)\bpass(?:word|wd)?\s*[:=]\s*['\"][^\s'\"]{6,}['\"]")),
]

# Credential lists ("username: x password: y") show up in notes/exports rather
# than code, so they need an unquoted pattern — but only where prose lives, or
# every `password:` field name in JS trips it.
DOC_SUFFIXES = {".md", ".txt", ".rtf", ".csv", ".rst"}
DOC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("credential list entry",
     re.compile(r"(?i)\buser(?:name)?\s*[:=]\s*\S+.{0,40}?\bpass(?:word|wd)?\s*[:=]\s*\S{6,}")),
]

# Files whose job is to *document* secret handling; matches there are expected.
SCAN_SKIP = re.compile(
    r"(^|/)(\.env\.example|uv\.lock|package-lock\.json|.*\.min\.js"
    r"|scripts/secret_inventory\.py|docs/SECURITY_THREAT_MODEL\.md)$"
)


def fingerprint(value: str) -> str:
    """Stable 8-hex-char identity for a secret, revealing nothing about it."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def inventory() -> int:
    print("Secret inventory (names, presence and fingerprints only)\n")
    missing_required = 0
    width = max(len(name) for name, *_ in SECRETS)
    for name, where, why, required in SECRETS:
        value = os.environ.get(name, "")
        if value:
            status = f"set   fp={fingerprint(value)} len={len(value)}"
        elif required:
            status = "MISSING (required in production)"
            missing_required += 1
        else:
            status = "unset"
        print(f"  {name:<{width}}  {status}")
        print(f"  {'':<{width}}  ↳ {where}: {why}")
    print(
        "\nRotate any of these that was ever pasted into a chat, printed to a log,\n"
        "committed, or packaged into an extension zip. Rotation = issue new, update\n"
        "the host secret, confirm the fingerprint changed, then revoke the old one."
    )
    return missing_required


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [ROOT / line for line in out if line]


def scan() -> int:
    """Scan tracked files for committed secrets. Returns the number of hits."""
    hits = 0
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if SCAN_SKIP.search(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable — nothing to match
        checks = list(PATTERNS)
        if path.suffix.lower() in DOC_SUFFIXES:
            checks += DOC_PATTERNS
        for label, pattern in checks:
            for m in pattern.finditer(text):
                line = text[: m.start()].count("\n") + 1
                # Report the location and the kind, never the matched value.
                print(f"  {rel}:{line}: possible {label}")
                hits += 1
    if hits:
        print(f"\n{hits} potential secret(s) in tracked files — review and rotate.")
    else:
        print("  no committed secrets matched the known patterns.")
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan-only", action="store_true")
    args = ap.parse_args()

    missing = 0 if args.scan_only else inventory()
    print("\nCommitted-secret scan (tracked files)\n")
    hits = scan()
    sys.exit(1 if hits else (0 if args.scan_only else min(missing, 1)))


if __name__ == "__main__":
    main()
