#!/usr/bin/env python3
"""CI gate: every navigation destination is a reviewed Ritaj URL.

`navigation.load_registry()` silently drops invalid rows — a malformed registry
must disable navigation, not take chat down. That makes a build-time gate
necessary, because "silently dropped" and "correct" look identical at runtime.

This validates the *raw file*, including entries that are disabled or awaiting
approval, and separates the two kinds of problem:

  ERROR  structural — a destination that is off-domain, non-https, carries
         credentials, traverses, or a duplicate/missing id. Fails the build.
  note   awaiting approval — `approved_by` empty and `enabled: false`. Expected
         while the registry is a review queue; reported, not failed.

It also fuzzes the validator against known URL attacks, so a future refactor
that loosens `_structural_problem` fails here rather than in front of a student.

Usage: python scripts/check_navigation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import navigation  # noqa: E402

# Attacks the validator must reject. Any accepted entry is a build failure.
HOSTILE_URLS = [
    ("https://www.birzeit.edu/en/admissions", "off-domain"),
    ("https://koha.birzeit.edu/", "off-domain sibling"),
    ("https://ritaj.birzeit.edu.attacker.test/reg/", "suffix trick"),
    ("https://evil-ritaj.birzeit.edu/reg/", "sibling subdomain"),
    ("https://attacker.test/ritaj.birzeit.edu/reg/", "host in path"),
    ("http://ritaj.birzeit.edu/reg/", "not https"),
    ("//ritaj.birzeit.edu/reg/", "scheme-relative"),
    ("javascript:alert(document.cookie)", "script scheme"),
    ("data:text/html,<script>alert(1)</script>", "data scheme"),
    ("https://user:pass@ritaj.birzeit.edu/reg/", "embedded credentials"),
    ("https://ritaj.birzeit.edu@attacker.test/", "userinfo confusion"),
    ("https://ritaj.birzeit.edu:8443/reg/", "non-standard port"),
    ("https://ritaj.birzeit.edu/reg/../../etc/passwd", "path traversal"),
    ("https://xn--ritj-hpa.birzeit.edu/reg/", "punycode homoglyph"),
    ("https://ritaj.birzeit.edu/reg/#javascript:alert(1)", "fragment"),
    ("https://ritaj.birzeit.edu\\@attacker.test/", "backslash"),
    ("https://ritaj.birzeit.edu/reg/ ?x=1", "whitespace"),
    ("https://ritaj.birzeit.edu/unregistered/path", "not in the registry"),
]


def check_file() -> tuple[int, int]:
    import yaml

    path = navigation.REGISTRY_PATH
    if not path.exists():
        print(f"  ERROR {path} does not exist")
        return 1, 0

    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(records, list):
        print("  ERROR navigation.yaml must contain a list of actions")
        return 1, 0

    errors = 0
    pending = 0
    seen_ids: set[str] = set()
    seen_destinations: dict[str, str] = {}

    for record in records:
        if not isinstance(record, dict):
            print("  ERROR non-mapping entry in navigation.yaml")
            errors += 1
            continue
        try:
            action = navigation.Action(**{
                k: v for k, v in record.items()
                if k in navigation.Action.__dataclass_fields__
            })
        except TypeError as exc:
            print(f"  ERROR malformed entry: {exc}")
            errors += 1
            continue

        for problem in navigation.problems(action):
            # An empty approver on a disabled action is the review queue's
            # normal state, not a defect.
            if "approved" in problem and not action.enabled:
                pending += 1
                print(f"  note  [{action.id}] awaiting approval (enabled: false)")
                continue
            print(f"  ERROR [{action.id}] {problem}")
            errors += 1

        if action.id in seen_ids:
            print(f"  ERROR [{action.id}] duplicate id")
            errors += 1
        seen_ids.add(action.id)

        # Two ids pointing at one page make rollback ambiguous: disabling one
        # leaves the other still opening it.
        key = navigation.canonical(action.destination)
        if key in seen_destinations:
            print(f"  ERROR [{action.id}] same destination as "
                  f"[{seen_destinations[key]}]")
            errors += 1
        else:
            seen_destinations[key] = action.id

        if action.enabled and not action.requires_confirmation:
            print(f"  ERROR [{action.id}] enabled without requires_confirmation")
            errors += 1

    print(f"\n  {len(records)} action(s), {pending} awaiting approval, {errors} error(s)")
    return errors, pending


def check_hostile() -> int:
    """The validator must reject every known attack shape."""
    errors = 0
    for url, why in HOSTILE_URLS:
        if navigation.validate_destination(url) is not None:
            print(f"  ERROR accepted {url!r} ({why})")
            errors += 1
    if not errors:
        print(f"  all {len(HOSTILE_URLS)} hostile URLs rejected")
    return errors


def main() -> None:
    print("Navigation registry\n")
    file_errors, pending = check_file()
    print("\nHostile-URL rejection\n")
    hostile_errors = check_hostile()

    total = file_errors + hostile_errors
    print()
    if total:
        sys.exit(f"FAILED: {total} problem(s).")
    if pending:
        print(f"OK — registry is valid. {pending} action(s) awaiting approval; "
              "navigation stays disabled until a reviewer enables them.")
    else:
        print("OK — every destination is a reviewed ritaj.birzeit.edu URL.")


if __name__ == "__main__":
    main()
