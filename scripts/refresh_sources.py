#!/usr/bin/env python3
"""Keep the corpus current — the half of it that can be automated.

## Why this is not a fetcher

The obvious tool here is a poller: hit `ritaj.birzeit.edu/academic-calendar` on a
schedule, diff it, re-index when it moves. That is not possible, and the reason
is not a missing feature.

Ritaj sits behind a Cloudflare managed challenge that answers **403 to every
automated request** — verified 2026-08-20 across `/`, `/academic-calendar` and
even `/robots.txt`, with and without a browser User-Agent. Defeating that
challenge is explicitly out of scope (`HANDBOOK.md` §5), and it would
also make this project's central promise false: that every indexed byte came
through an authorized path a named person approved.

So one step stays human — a person opens the page in a real browser and saves
it. Everything either side of that step is automated here:

    --report    which sources are overdue, and by how long        (the reminder)
    --update    take a saved file, decide whether anything changed (the diff)

## What --update actually decides

Comparing hashes answers a question that matters more than "is it time to look
again": **did the content actually move?**

  * unchanged -> the snapshot is byte-identical, so the approval still describes
    exactly what is indexed. `fetched_at` is bumped, approval is untouched, and
    the record stops being stale. Nobody re-reviews text they already reviewed.
  * changed   -> approval described the OLD bytes. It is withdrawn
    (`approved: false`) and the record leaves the index until a human re-reads
    the diff and re-approves. Silently re-indexing changed text under an old
    approval is precisely the failure the sha256 field exists to catch.

Usage:
    python scripts/refresh_sources.py --report
    python scripts/refresh_sources.py --report --json out.json
    python scripts/refresh_sources.py --update academic-calendar-en ~/Downloads/calendar.html
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import source_policy  # noqa: E402

DATA = ROOT / "data"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


# --- report -------------------------------------------------------------------
def report(as_json: Path | None) -> int:
    """Which approved sources are past their refresh window.

    Staleness was already computed and shown to *students* — a badge on an
    answer. Nobody was ever told to go and fix it, so the badge could only ever
    appear and stay. This is the operator-facing half.
    """
    result = source_policy.load_and_validate(check_content=False)
    approved = [s for s in result.sources if s.approved]
    today = date.today()

    rows = []
    for source in approved:
        deadline = source.stale_after()
        overdue = (today - deadline).days if deadline and today > deadline else 0
        rows.append({
            "id": source.id,
            "title": source.title,
            "refresh": source.refresh,
            "fetched_at": source.fetched_at,
            "stale_after": deadline.isoformat() if deadline else None,
            "overdue_days": overdue,
            "stale": source.is_stale(today),
            "url": source.canonical_url,
        })
    rows.sort(key=lambda r: (-r["overdue_days"], r["id"]))

    print(f"Corpus freshness — {today.isoformat()}\n")
    if not approved:
        print("  No approved sources. Nothing can be stale, and nothing can be served.")
        print("  This is not a clean bill of health — see HANDBOOK.md §5.")
    else:
        width = max(len(r["id"]) for r in rows)
        for row in rows:
            if row["overdue_days"] > 0:
                state = f"OVERDUE by {row['overdue_days']}d"
            elif row["stale"]:
                state = "STALE"
            else:
                state = "fresh"
            print(f"  {row['id']:<{width}}  {row['refresh']:<8} "
                  f"fetched {row['fetched_at'] or '—':<12} {state}")
        print()
        overdue = [r for r in rows if r["overdue_days"] > 0]
        if overdue:
            print(f"  {len(overdue)} source(s) need re-saving from a browser:")
            for row in overdue:
                print(f"    {row['url']}")
            print("\n  Then: python scripts/refresh_sources.py --update <id> <saved-file>")

    if as_json:
        as_json.write_text(json.dumps(
            {"generated_on": today.isoformat(), "sources": rows}, indent=2) + "\n",
            encoding="utf-8")
        print(f"\n  wrote {as_json}")

    # Exit 1 when something is overdue, so a scheduled run is actionable rather
    # than something to read. Never fails on "no corpus" — that is B2's problem,
    # reported by check_corpus_policy.py, and duplicating it here would mean two
    # red jobs for one cause.
    return 1 if any(r["overdue_days"] > 0 for r in rows) else 0


# --- update -------------------------------------------------------------------
def update(source_id: str, saved: Path) -> int:
    if not saved.is_file():
        print(f"ERROR {saved} is not a file")
        return 1

    result = source_policy.load_and_validate(check_content=False)
    source = next((s for s in result.sources if s.id == source_id), None)
    if source is None:
        print(f"ERROR no record with id {source_id!r} in data/sources.yaml")
        print(f"      known ids: {', '.join(sorted(s.id for s in result.sources))}")
        return 1

    new_hash = _sha256(saved)
    old_hash = source.sha256 or ""

    print(f"Record   : {source.id}")
    print(f"Canonical: {source.canonical_url}")
    print(f"Recorded : {old_hash[:16] + '…' if old_hash else '(none — first snapshot)'}")
    print(f"Saved    : {new_hash[:16]}…")
    print()

    if old_hash and new_hash == old_hash:
        # The bytes are identical, so the existing approval still describes
        # exactly what is indexed. Re-approving would be theatre.
        _write_fields(source_id, {"fetched_at": date.today().isoformat()})
        print("UNCHANGED — the page has not moved since it was approved.")
        print(f"  fetched_at bumped to {date.today().isoformat()}; approval untouched.")
        print("  Nothing to re-index, nothing to re-review.")
        return 0

    # Place the new snapshot alongside the corpus version it belongs to.
    target_rel = source.content_path or f"snapshots/{date.today().isoformat()}/{source.id}{saved.suffix}"
    target = DATA / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(saved, target)

    _write_fields(source_id, {
        "content_path": target_rel,
        "sha256": new_hash,
        "fetched_at": date.today().isoformat(),
        # Withdrawn deliberately. The old approval described the old bytes; a
        # human has not seen these. Indexing them under the previous sign-off is
        # exactly what the checksum exists to prevent.
        "approved": False,
    })

    print("CHANGED — the page differs from the approved snapshot.")
    print(f"  snapshot written to data/{target_rel}")
    print("  approval WITHDRAWN: this record has left the index until re-approved.")
    print()
    print("  Next:")
    print(f"    1. read the new snapshot — data/{target_rel}")
    print("    2. confirm no personal data, no placeholder text, dates still correct")
    print(f"    3. set approved: true and approved_by: <your name> on {source_id}")
    print("    4. python scripts/check_corpus_policy.py --release")
    print("    5. python scripts/build_index.py --publish && deploy")
    return 0


def _write_fields(source_id: str, fields: dict) -> None:
    """Rewrite one record's fields in data/sources.yaml, preserving everything else.

    Edits the parsed document rather than the text, so comments elsewhere in the
    file are the only casualty — and this file's comments live in a header block
    that yaml.safe_dump does not reach anyway. A regex edit of a YAML record is
    the alternative, and it is worse.
    """
    import yaml  # noqa: PLC0415

    path = source_policy.SOURCES_PATH
    records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    for record in records:
        if record.get("id") == source_id:
            record.update(fields)
            break
    path.write_text(
        yaml.safe_dump(records, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", action="store_true",
                       help="list approved sources and which are overdue")
    group.add_argument("--update", nargs=2, metavar=("SOURCE_ID", "SAVED_FILE"),
                       help="record a newly saved snapshot for one source")
    ap.add_argument("--json", type=Path, default=None,
                    help="also write the report as JSON (for a dashboard or a cron)")
    args = ap.parse_args()

    if args.report:
        return report(args.json)
    return update(args.update[0], Path(args.update[1]).expanduser())


if __name__ == "__main__":
    raise SystemExit(main())
