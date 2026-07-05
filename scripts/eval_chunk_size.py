"""Chunking evaluation: sweep word-window sizes and compare window vs
structure-aware chunking on dense retrieval recall.

The logic lives in ritaj.evaluation (shared with the /viz Eval tab); this is just
the CLI view. Re-chunks + re-embeds the corpus and scores by exact cosine per
configuration (the live Qdrant index is never touched).

Metrics: R@1/3/5 (gold span in top-k) and MRR.

Usage:  .venv/bin/python scripts/eval_chunk_size.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj.evaluation import run_chunking_eval  # noqa: E402


def main() -> None:
    res = run_chunking_eval()

    print(f"\n{'size':>5} {'#chunks':>8} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'MRR':>7}")
    print("-" * 48)
    for r in res["sweep"]:
        print(f"{r['size']:>5} {r['chunks']:>8} {r['r1']:>6.2f} {r['r3']:>6.2f} "
              f"{r['r5']:>6.2f} {r['mrr']:>7.3f}")

    best = max(res["sweep"], key=lambda r: (r["mrr"], -r["size"]))
    print(f"\nBest by MRR: {best['size']} words/chunk (MRR={best['mrr']:.3f})")

    print("\n" + "#" * 48)
    print("Window-120 vs structure-aware chunking")
    print("#" * 48)
    print(f"\n{'strategy':>18} {'#chunks':>8} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'MRR':>7}")
    print("-" * 56)
    for r in res["strategies"]:
        print(f"{r['label']:>18} {r['chunks']:>8} {r['r1']:>6.2f} {r['r3']:>6.2f} "
              f"{r['r5']:>6.2f} {r['mrr']:>7.3f}")


if __name__ == "__main__":
    main()
