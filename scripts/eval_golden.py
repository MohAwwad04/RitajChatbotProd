"""End-to-end golden-set evaluation (plan section 13).

Runs the FULL live pipeline (retrieve -> answer -> grounding -> repair) over every
case in the golden set and scores answer quality. The logic lives in
ritaj.evaluation (shared with the /viz Eval tab); this is just the CLI view.

Needs the embedder + reranker AND a running LLM, so it's slow (~one LLM call per
case). The cheap model-free checks live in tests/test_smoke.py.

Usage:  .venv/bin/python scripts/eval_golden.py [--judge]
          --judge  also run the LLM-as-judge (faithfulness + citation
                   correctness) — a second LLM call per answerable case.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj.evaluation import run_golden  # noqa: E402


def main() -> None:
    judge = "--judge" in sys.argv
    res = run_golden(judge=judge)
    s = res["summary"]
    print(f"Golden set: {len(res['cases'])} cases "
          f"({s['answerable']} answerable, {s['refusal']} refusal)\n"
          "Running the full pipeline per case — this is slow.\n")

    mark = lambda b: " ✓ " if b else " ✗ "
    print(f"{'retr':>4} {'ans':>4} {'grnd':>5}  question")
    print("-" * 64)
    for c in res["cases"]:
        if c["type"] == "answerable":
            print(f"{mark(c['retrieval'])} {mark(c['answer'])} "
                  f"{mark(c['grounded']):>5}  {c['q'][:46]}")

    print(f"\n{'refused':>8}  question")
    print("-" * 64)
    for c in res["cases"]:
        if c["type"] == "refuse":
            print(f"{mark(c['refused']):>8}  {c['q'][:46]}")

    print("\n" + "=" * 64)
    print("ANSWERABLE")
    print(f"  retrieval@k (right source found) : {s['retrieval_pct']}%")
    print(f"  answer accuracy (gold fact shown): {s['accuracy_pct']}%")
    print(f"  groundedness (verdict=grounded)  : {s['grounded_pct']}%")
    print(f"  false-refusal (want 0)           : {s['false_refusal_pct']}%")
    print("REFUSAL")
    print(f"  refused correctly                : {s['refused_pct']}%")
    print(f"  hallucinated (want 0)            : {s['hallucinated_pct']}%")
    if judge:
        print("LLM-AS-JUDGE")
        print(f"  faithful (claims in sources)     : {s['judge_faithful_pct']}%")
        print(f"  citations correct                : {s['judge_citations_pct']}%")
    print("=" * 64)


if __name__ == "__main__":
    main()
