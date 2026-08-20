#!/usr/bin/env python3
"""Generate the extension's bundled copy of the reviewed navigation registry.

Why a bundled copy exists at all
-------------------------------
The page-finder is the only feature that can be useful before an approved corpus
exists, and it is the feature most likely to be asked for during an outage — a
student opens the panel precisely because they cannot find a page. Making it
depend on a reachable backend means it fails at the moment it is needed.

So the extension ships the destinations. `/v2/navigation/actions` is the fresher
answer when the network is available (and is how a bad destination is withdrawn
without a Chrome Web Store review), but the bundled copy is what answers when
the Space is asleep, the corpus is absent, or the student is offline.

Why it is generated rather than written
---------------------------------------
Two hand-maintained copies of a security-relevant allowlist is a drift bug with
a schedule. This script is the only writer; `scripts/check_extension.py` fails
the build when the generated file disagrees with `data/navigation.yaml`, so the
copy cannot silently rot the way `MAX_MESSAGE_CHARS` once did.

Only `enabled: true` actions are emitted. A candidate awaiting approval is not a
destination, and shipping one to a client — even disabled — would put an
unreviewed URL inside a published artifact.

Usage:
    python scripts/sync_extension_actions.py            # write the file
    python scripts/sync_extension_actions.py --check    # exit 1 if it drifted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import navigation  # noqa: E402

TARGET = ROOT / "chrome-extension" / "actions.generated.js"

HEADER = """\
// GENERATED FILE — do not edit by hand.
//
// Written by scripts/sync_extension_actions.py from data/navigation.yaml, and
// checked by scripts/check_extension.py, which fails the build if this file and
// the registry disagree.
//
// This is the extension's offline copy of the reviewed destinations. It is what
// makes the page-finder work when the backend is unreachable — asleep, mid
// redeploy, or deliberately `not-ready` because no corpus has been approved yet.
// When the network IS available the panel prefers /v2/navigation/actions, so a
// destination can be withdrawn server-side without waiting for a Store review.
//
// Only approved, enabled actions appear here. Every URL in this file is still
// validated by navigation.js before chrome.tabs.create() is called: a generated
// file is not a trusted file, and the point of the client-side check is that it
// does not trust its own inputs either.
"""


def build() -> str:
    """Render the module source from the registry."""
    actions = sorted(
        (a for a in navigation.load_registry().values() if a.enabled),
        key=lambda a: a.id,
    )
    payload = [
        {
            "id": a.id,
            "label_ar": a.label_ar,
            "label_en": a.label_en,
            "url": a.destination,
            "auth_required": a.auth_required,
            "requires_confirmation": a.requires_confirmation,
            "intents_ar": a.intents_ar,
            "intents_en": a.intents_en,
            "min_confidence": a.min_confidence,
        }
        for a in actions
    ]
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    # Indent the array one level so it reads as part of the export.
    body = "\n".join(("  " + line) if line else line for line in body.splitlines())
    count = len(payload)
    note = (
        "// No destination is approved yet: every action in data/navigation.yaml is\n"
        "// `enabled: false` with an empty `approved_by`, pending a human opening each\n"
        "// URL in a signed-out browser. The panel renders no page-finder buttons in\n"
        "// this state, which is the honest outcome — see cowork_ritaj/human-actions.md\n"
        "// section H4.\n"
        if count == 0
        else f"// {count} approved destination{'s' if count != 1 else ''}.\n"
    )
    return (
        f"{HEADER}//\n{note}\n"
        f"export const REGISTRY_VERSION = '{navigation.registry_version()}'\n\n"
        f"export const BUNDLED_ACTIONS = {body.lstrip()}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 if the file differs from the registry",
    )
    args = parser.parse_args()

    generated = build()
    current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else None

    if args.check:
        if current == generated:
            enabled = sum(1 for a in navigation.load_registry().values() if a.enabled)
            print(
                f"OK — {TARGET.relative_to(ROOT)} matches data/navigation.yaml "
                f"({enabled} enabled, version {navigation.registry_version()})"
            )
            return 0
        if current is None:
            print(f"ERROR {TARGET.relative_to(ROOT)} does not exist")
        else:
            print(
                f"ERROR {TARGET.relative_to(ROOT)} has drifted from data/navigation.yaml.\n"
                "      Run: python scripts/sync_extension_actions.py"
            )
        return 1

    TARGET.write_text(generated, encoding="utf-8")
    enabled = sum(1 for a in navigation.load_registry().values() if a.enabled)
    print(
        f"Wrote {TARGET.relative_to(ROOT)} — {enabled} enabled action(s), "
        f"version {navigation.registry_version()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
