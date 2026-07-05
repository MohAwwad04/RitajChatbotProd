"""Grounding-threshold tuning (plan section 13).

Sweeps the grounding support-threshold over the answerable golden cases and shows
how many genuinely-correct answers pass at each value. Use it to pick
grounding.SUPPORT_THRESHOLD honestly instead of guessing: too high needlessly
flags correct answers, too low lets weak ones through.

The live pipeline (retrieve + answer) runs once per case; only the cheap
re-grounding repeats per threshold. Needs the embedder + a running LLM.

Usage:  .venv/bin/python scripts/eval_threshold.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj.evaluation import tune_threshold  # noqa: E402


def main() -> None:
    res = tune_threshold()
    print(f"Grounding-threshold sweep over {res['n_correct_drafts']} correct drafts "
          f"(current default = {res['current']})\n")
    print(f"{'threshold':>9}  {'grounded':>8}  share")
    print("-" * 40)
    for row in res["rows"]:
        bar = "#" * round((row["grounded_pct"] or 0) / 5)
        star = "  <- current" if abs(row["threshold"] - res["current"]) < 1e-9 else ""
        print(f"{row['threshold']:>9.2f}  {row['grounded_of_correct']:>8}  "
              f"{row['grounded_pct']:>3}% {bar}{star}")


if __name__ == "__main__":
    main()
