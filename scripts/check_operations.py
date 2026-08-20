#!/usr/bin/env python3
"""CI gate: every operational duty has a named owner, every drill a date.

`docs/OPERATIONS.md` §1 lists nine duties, each needing a primary and a backup,
and §4 lists four drills that must be rehearsed before the pilot. Both tables
ship entirely blank. Prose cannot enforce itself: a blank Primary cell reads
exactly like a filled one to everybody except the person who needed to be paged
at 2am, and a rollback that has never been performed is a plan, not a capability.

The tables are parsed, not read. A row is complete when:

  §1  Primary and Backup are both non-empty and are not placeholders
      ("TBD", "team", "us", "-"). A collective noun is not an owner — when
      everybody is responsible, nobody is paged.
  §4  Rehearsed carries a date and Recovery time carries a duration.

Exit 1 while anything is blank, naming each row. That is the intended state
today; it turns green when Stream 6 of the Cowork plan fills the register in.

Usage:
    python scripts/check_operations.py
    python scripts/check_operations.py --path docs/OPERATIONS.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "docs" / "OPERATIONS.md"

# Words that occupy a cell without answering it. Deliberately includes the
# plausible-sounding ones: "the team" and "maintainers" are how an unassigned
# duty passes a review.
PLACEHOLDERS = {
    "", "-", "—", "–", "tbd", "tba", "todo", "n/a", "na", "none", "?", "???",
    "team", "the team", "us", "everyone", "anyone", "maintainers",
    "the maintainers", "project team", "whoever", "someone",
}

# A date in the register may be written a few ways; all that matters is that it
# names a real day rather than "soon".
DATE = re.compile(
    r"\d{4}-\d{2}-\d{2}"                                  # 2026-08-15
    r"|\d{1,2}\s+\w+\s+\d{4}"                             # 15 August 2026
    r"|\w+\s+\d{1,2},?\s+\d{4}",                          # August 15, 2026
)
# "12 min", "4m30s", "01:20", "2 hours" — a measurement, not an adjective.
DURATION = re.compile(r"\d+\s*(?:s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours)\b"
                      r"|\d{1,2}:\d{2}", re.I)


def _rows(markdown: str, heading: str) -> list[list[str]]:
    """Cells of every data row in the first table under `heading`."""
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().startswith(heading))
    except StopIteration:
        return []

    rows: list[list[str]] = []
    seen_table = False
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("## ") and seen_table:
            break
        if not stripped.startswith("|"):
            if seen_table and rows:
                break  # the table ended
            continue
        seen_table = True
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        # Skip the header and its |---|---| separator.
        if set("".join(cells)) <= set("-: "):
            continue
        if cells and cells[0].lower() in {"duty", "drill"}:
            continue
        rows.append(cells)
    return rows


def _blank(cell: str) -> bool:
    return cell.strip().strip("*_` ").lower() in PLACEHOLDERS


def check_ownership(markdown: str) -> int:
    rows = _rows(markdown, "## 1.")
    if not rows:
        print("  ERROR could not find the ownership register (§1)")
        return 1

    problems = 0
    for cells in rows:
        duty = cells[0]
        primary = cells[1] if len(cells) > 1 else ""
        backup = cells[2] if len(cells) > 2 else ""
        missing = [name for name, cell in (("primary", primary), ("backup", backup))
                   if _blank(cell)]
        if missing:
            print(f"  ERROR [{duty}] has no {' and no '.join(missing)}")
            problems += 1

    if not problems:
        print(f"  {len(rows)} duties, each with a named primary and backup")
    return problems


def check_drills(markdown: str) -> int:
    rows = _rows(markdown, "## 4.")
    if not rows:
        print("  ERROR could not find the rehearsal table (§4)")
        return 1

    problems = 0
    for cells in rows:
        drill = cells[0]
        rehearsed = cells[1] if len(cells) > 1 else ""
        recovery = cells[2] if len(cells) > 2 else ""
        if _blank(rehearsed) or not DATE.search(rehearsed):
            print(f"  ERROR [{drill}] has not been rehearsed on a recorded date")
            problems += 1
        elif _blank(recovery) or not DURATION.search(recovery):
            # Only worth asking once the drill happened at all.
            print(f"  ERROR [{drill}] records no recovery time")
            problems += 1

    if not problems:
        print(f"  {len(rows)} drills, each rehearsed with a recorded recovery time")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=str(OPERATIONS))
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        sys.exit(f"FAILED: {path} does not exist.")
    markdown = path.read_text(encoding="utf-8")

    print("Ownership register\n")
    problems = check_ownership(markdown)
    print("\nRehearsal record\n")
    problems += check_drills(markdown)

    print()
    if problems:
        sys.exit(
            f"FAILED: {problems} unassigned duty/unrehearsed drill. These need a "
            "person, not a code change — see cowork_ritaj/COWORK_PLAN.md §7."
        )
    print("OK — every duty is owned and every drill has been rehearsed.")


if __name__ == "__main__":
    main()
