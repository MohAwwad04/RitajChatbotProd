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
    from ritaj import navigation

    for case in (data.get("adversarial_url") or []):
        # validate_destination returns the URL when it may be opened, and None
        # when it may not. A hostile URL must come back None.
        if navigation.validate_destination(case["url"]) is not None:
            print(f"  MISS  accepted {case['url']!r} ({case['why']})")
            failures += 1
    print(f"  checked {len(data.get('adversarial_url') or [])} case(s)\n")

    failures += score_navigation(data)
    return failures


def score_navigation(data: dict) -> int:
    """Resolve every navigation intent and score destination precision.

    The registry ships with every action `enabled: false` — correctly, because
    no destination has a human approver yet. That would make every case resolve
    to nothing and the suite pass vacuously, so the registry is enabled *for the
    duration of this check*: what is being measured is whether the resolver maps
    intents to the right action, which is a property of the resolver and the
    intent phrases, not of the approval state.

    Precision is reported separately from recall because they are not equally
    serious. A missed match means a student does not get a button. A WRONG match
    opens a page they did not ask for.
    """
    cases = data.get("navigation") or []
    if not cases:
        print("Navigation intent resolution\n\n  (no cases yet)\n")
        return 0

    from ritaj import navigation

    print("Navigation intent resolution\n")

    registry = {action_id: _enabled(action)
                for action_id, action in _raw_registry().items()}

    resolved_wrong = 0
    missed = 0
    for case in cases:
        expected = case["expect"]
        with _registry(registry):
            action = navigation.resolve(case["q"], locale=case.get("lang", "en"))
        got = action["id"] if action else "none"

        if got == expected:
            continue
        if expected == "none" or got != "none":
            # Either it offered a destination where it should have offered
            # none, or it offered the wrong one. Both are precision failures.
            print(f"  WRONG  {case['q']!r} -> {got} (expected {expected})")
            resolved_wrong += 1
        else:
            print(f"  MISS   {case['q']!r} -> none (expected {expected})")
            missed += 1

    should_resolve = sum(1 for c in cases if c["expect"] != "none")
    offered = should_resolve - missed
    precision = 1.0 if (offered + resolved_wrong) == 0 else offered / (offered + resolved_wrong)
    recall = 1.0 if should_resolve == 0 else offered / should_resolve

    print(f"\n  {len(cases)} case(s): destination precision {precision:.0%}, "
          f"intent recall {recall:.0%}")

    threshold = (data.get("thresholds") or {}).get("navigation_precision", 1.0)
    if precision < threshold:
        print(f"  FAILED precision {precision:.0%} < required {threshold:.0%}")
        return 1
    if missed:
        print(f"  note: {missed} intent(s) matched nothing — a student gets no "
              "button, which is safe but less useful")
    print()
    return 0


def _raw_registry():
    from ritaj import navigation
    import yaml

    records = yaml.safe_load(navigation.REGISTRY_PATH.read_text(encoding="utf-8")) or []
    out = {}
    for record in records:
        action = navigation.Action(**{
            k: v for k, v in record.items()
            if k in navigation.Action.__dataclass_fields__
        })
        out[action.id] = action
    return out


def _enabled(action):
    import dataclasses

    return dataclasses.replace(action, enabled=True, approved_by=action.approved_by or "eval")


class _registry:
    """Temporarily swap in a registry, restoring the real one afterwards."""

    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        from ritaj import navigation

        self._original = navigation.load_registry
        navigation.load_registry = lambda *a, **k: self.registry
        return self

    def __exit__(self, *exc):
        from ritaj import navigation

        navigation.load_registry = self._original
        return False


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
