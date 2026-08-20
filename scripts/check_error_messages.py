#!/usr/bin/env python3
"""CI gate: every public error code has student-facing wording in every client.

The failure this exists to catch, observed twice in one afternoon:

  1. The portal had no per-code table at all. It discarded the backend's code
     and message and rendered one sentence — "Couldn't reach the assistant right
     now. Please try again." — for every possible cause, including causes where
     retrying can never help.
  2. When `NO_CORPUS` was added to errors.py, the extension did not know it and
     silently fell back to its generic line. Nothing failed; the message was
     just wrong, which is the worst way for this to go wrong.

A code without wording is not a crash. It is a client confidently telling a
student something untrue about why the product did not work, which is exactly
the class of problem `check_privacy.py` exists to prevent elsewhere.

Both clients are also required to carry the transport codes — the failures where
no response arrived at all, so the server never got a chance to name a reason.

Usage: python scripts/check_error_messages.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EXTENSION = ROOT / "chrome-extension" / "sidepanel.js"
PORTAL_I18N = ROOT / "ritaj-student-portal" / "src" / "i18n.ts"

# Codes the server can return that a client should never surface verbatim.
# INTERNAL is deliberately excluded: it is the catch-all for an unexpected
# exception, and each client's generic fallback is the correct treatment.
NOT_STUDENT_FACING = {"INTERNAL"}

# Failures where no response arrived, so no server code exists. Classified by
# the clients themselves (describeTransportFailure / statusCode), and every one
# still needs wording or the classification buys nothing.
TRANSPORT_CODES = {
    "OFFLINE", "TIMEOUT", "UNREACHABLE",
    "STARTING_OR_ASLEEP", "GATEWAY", "HTTP_ERROR", "UNKNOWN",
}


def server_codes() -> set[str]:
    """Every public error code errors.py defines."""
    from ritaj import errors  # noqa: PLC0415

    return {
        name for name, value in vars(errors).items()
        if name.isupper() and callable(value) and not name.startswith("_")
    } - NOT_STUDENT_FACING


def _codes_in(text: str, block_pattern: str) -> set[str]:
    """Code keys declared inside the named object literal."""
    match = re.search(block_pattern, text, re.S)
    if not match:
        return set()
    return set(re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*:", match.group(1), re.M))


def check_client(path: Path, block_pattern: str, label: str, required: set[str]) -> int:
    if not path.exists():
        print(f"  ERROR {label}: {path.relative_to(ROOT)} not found")
        return 1
    text = path.read_text(encoding="utf-8")

    # Both languages must carry the same set — an Arabic-first product that
    # falls back to English on failure is failing the students it serves most.
    blocks = re.findall(block_pattern, text, re.S)
    if not blocks:
        print(f"  ERROR {label}: could not find the error-message table")
        return 1

    errors_found = 0
    for index, block in enumerate(blocks, start=1):
        declared = set(re.findall(r"^\s*([A-Z][A-Z0-9_]+)\s*:", block, re.M))
        missing = sorted(required - declared)
        for code in missing:
            print(f"  ERROR {label} (table {index}/{len(blocks)}): no wording for {code}")
            errors_found += 1

    if len(blocks) < 2:
        print(f"  ERROR {label}: expected an Arabic and an English table, found {len(blocks)}")
        errors_found += 1

    if not errors_found:
        print(f"  {label} OK — {len(blocks)} language table(s), all {len(required)} codes covered")
    return errors_found


def main() -> None:
    required = server_codes() | TRANSPORT_CODES
    print(f"Error-message coverage ({len(required)} codes)\n")

    errors_found = 0
    errors_found += check_client(
        EXTENSION, r"codes:\s*\{(.*?)\n    \},", "extension", required)
    errors_found += check_client(
        PORTAL_I18N, r"error_codes:\s*\{(.*?)\n    \}", "portal", required)

    print()
    if errors_found:
        sys.exit(
            f"FAILED: {errors_found} problem(s). A code with no wording means a client "
            "tells a student something untrue about why the product did not work."
        )
    print("OK — every public error code has wording in every client, in both languages.")


if __name__ == "__main__":
    main()
