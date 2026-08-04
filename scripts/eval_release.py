#!/usr/bin/env python3
"""Run (or gate on) the release evaluation set.

Two modes, because they answer different questions:

    --gate    Is the release set complete enough to release against?
              Model-free, runs in CI, fails while a required category is short.
    (default) Run the model-free parts of the set: scope refusals, injection
              redaction, and URL rejection. These need no LLM and no corpus.

The corpus-dependent categories (answerable, calendar, navigation) need a live
model and an approved index; they are scored by scripts/eval_golden.py once
those exist.

Usage:
    python scripts/eval_release.py --gate
    python scripts/eval_release.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SET_PATH = ROOT / "data" / "eval" / "release_set.yaml"


def load() -> dict:
    import yaml

    return yaml.safe_load(SET_PATH.read_text(encoding="utf-8"))


def gate(data: dict) -> int:
    """Fail while the set is too small to support the release thresholds."""
    problems = 0
    print("Release-set completeness\n")
    for category, required in data["required_counts"].items():
        have = len(data.get(category) or [])
        status = "OK " if have >= required else "SHORT"
        if have < required:
            problems += 1
        print(f"  {status} {category:<14} {have:>4} / {required}")

    extra = {k: len(data.get(k) or []) for k in
             ("adversarial_query", "adversarial_source", "adversarial_url")}
    print("\nAdversarial coverage (no fixed minimum, but must be non-empty)")
    for name, count in extra.items():
        print(f"  {'OK ' if count else 'EMPTY'} {name:<20} {count:>4}")
        if not count:
            problems += 1

    if problems:
        print(
            f"\n{problems} category/categories incomplete. The corpus-dependent ones "
            "(answerable, calendar, navigation) are blocked on an approved Ritaj "
            "corpus — see data/quarantine/README.md."
        )
    return problems


def run_model_free(data: dict) -> int:
    """Score the parts that need neither an LLM nor an index."""
    from ritaj import guardrails

    failures = 0

    print("Scope refusals (personal data / out of scope)\n")
    checked = 0
    for case in (data.get("personal_data") or []):
        if case["expect"] not in ("refuse_personal", "refuse_transaction"):
            continue
        checked += 1
        result = guardrails.check_scope(case["q"])
        if case["expect"] == "refuse_personal" and result["category"] != "personal_data":
            print(f"  MISS  {case['q']!r} -> allowed={result['allowed']} "
                  f"category={result['category']}")
            failures += 1
        elif case["expect"] == "refuse_personal":
            # Refusals must be in the student's language.
            is_arabic = case["lang"] == "ar"
            has_arabic = any("؀" <= ch <= "ۿ" for ch in result["response"])
            if is_arabic != has_arabic:
                print(f"  LANG  {case['q']!r} answered in the wrong language")
                failures += 1
    print(f"  checked {checked} case(s)\n")

    print("Indirect injection redaction\n")
    for case in (data.get("adversarial_source") or []):
        passages = [(f"Registration info.\n{case['planted']}\nMore info.", {"title": "t"})]
        clean, report = guardrails.sanitize(passages)
        if not report["detected"] or case["planted"] in clean[0][0]:
            print(f"  MISS  planted text survived: {case['planted'][:60]!r}")
            failures += 1
    print(f"  checked {len(data.get('adversarial_source') or [])} case(s)\n")

    print("Navigation URL rejection\n")
    try:
        from ritaj import navigation
    except ImportError:
        print("  navigation module not present yet — skipped")
        navigation = None
    if navigation is not None:
        for case in (data.get("adversarial_url") or []):
            # validate_destination returns the URL when it may be opened, and
            # None when it may not. A hostile URL must come back None.
            if navigation.validate_destination(case["url"]) is not None:
                print(f"  MISS  accepted {case['url']!r} ({case['why']})")
                failures += 1
        print(f"  checked {len(data.get('adversarial_url') or [])} case(s)\n")

    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="store_true",
                    help="check completeness only (model-free, for CI)")
    args = ap.parse_args()

    data = load()
    if args.gate:
        sys.exit(1 if gate(data) else 0)

    failures = run_model_free(data)
    if failures:
        sys.exit(f"{failures} model-free release check(s) failed.")
    print("All model-free release checks passed.")


if __name__ == "__main__":
    main()
