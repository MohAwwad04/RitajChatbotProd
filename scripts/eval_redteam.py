"""Red-team evaluation — does the assistant hold under adversarial input?

Where eval_golden.py measures answer *quality* on honest questions, this measures
*safety* under hostile ones. It drives the FULL production pipeline (api.chat:
scope guardrail -> retrieve/inject -> sanitize -> answer -> grounding -> repair)
over a labelled attack set spanning four families:

  prompt_injection    query-side + indirect (override planted in a source chunk)
  exfiltration        personal records without auth + system-prompt leak
  hallucination_bait  facts not in the corpus + false premises
  harmful_jailbreak   harmful requests + DAN/roleplay jailbreaks

The shared logic lives in ritaj.evaluation.run_redteam (also exposed at
/admin/eval/redteam); this is the CLI view. Needs the embedder + reranker AND a
running LLM, so it is slow (~one LLM call per case). The cheap, model-free
adversarial checks live in tests/test_redteam.py and run in CI.

Usage:  .venv/bin/python scripts/eval_redteam.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj.evaluation import run_redteam  # noqa: E402


def main() -> None:
    res = run_redteam()
    s = res["summary"]
    print(f"Red-team set: {s['n']} adversarial cases across "
          f"{len(s['by_category'])} attack families.\n"
          "Running the full production pipeline per case — this is slow.\n")

    mark = lambda b: " ✓ " if b else " ✗✗"  # a failed defense should stand out
    print(f"{'held':>4}  {'category':<18} {'verdict':<10}  attack")
    print("-" * 78)
    for c in res["cases"]:
        flags = []
        if c["leaked"]:
            flags.append("LEAKED")
        if c["forbidden"]:
            flags.append("FORBIDDEN:" + ",".join(c["forbidden"]))
        if c.get("blocked"):
            flags.append(f"blocked={c['blocked']}")
        suffix = ("  [" + " ".join(flags) + "]") if flags else ""
        print(f"{mark(c['held'])}  {c['category']:<18} {str(c['verdict']):<10}  "
              f"{c['q'][:40]}{suffix}")

    print("\n" + "=" * 78)
    print("BY FAMILY (held = attack fully withstood)")
    for cat, m in s["by_category"].items():
        bar = "#" * round((m["held_pct"] or 0) / 5)
        print(f"  {cat:<20} {m['held']:>2}/{m['n']:<2}  {m['held_pct']:>3}% {bar}")
    print("OVERALL")
    print(f"  held (want 100)                  : {s['held']}/{s['n']} = {s['held_pct']}%")
    print(f"  system-prompt leaks (want 0)     : {s['leaked']}")
    print("=" * 78)

    # Non-zero exit if any defense failed, so CI / a pre-deploy gate can use it.
    sys.exit(0 if s["held"] == s["n"] and s["leaked"] == 0 else 1)


if __name__ == "__main__":
    main()
