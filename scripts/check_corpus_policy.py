#!/usr/bin/env python3
"""CI gate: nothing off-domain, unapproved or fabricated reaches an index.

Runs on every pull request. Three checks, each of which has already failed in
this project's history:

  1. **Manifest validity** — every record in data/sources.yaml parses and obeys
     the source policy (https, host exactly ritaj.birzeit.edu, hash matches
     stored content, approved records name an approver, no PII).
  2. **No smuggled corpus** — no indexable file has appeared outside the
     approved paths. `data/raw/` used to be a folder scan; a stray Markdown file
     dropped there once went straight into production.
  3. **Published artifact integrity** — if data/corpus/CURRENT points somewhere,
     that artifact exists, its manifest parses, and every chunk in it traces to
     an approved `ritaj.birzeit.edu` source.

Exit 0 = clean. Exit 1 = a human has to look.

Usage:
    python scripts/check_corpus_policy.py
    python scripts/check_corpus_policy.py --strict   # also fail on warnings
    python scripts/check_corpus_policy.py --release  # also fail if it checked nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import corpus, source_policy  # noqa: E402

DATA = ROOT / "data"
# Folders whose Markdown/PDF may never be indexed by a production build.
NON_CORPUS_DIRS = ("quarantine", "snapshots", "corpus")
INDEXABLE_SUFFIXES = {".md", ".txt", ".pdf"}


def check_manifest(strict: bool) -> tuple[int, int, int]:
    """Returns (fatal, counted_warnings, approved_records_validated)."""
    report = source_policy.load_and_validate()
    fatal = [p for p in report.problems if p.fatal]
    warnings = [p for p in report.problems if not p.fatal]

    print(f"manifest: {len(report.sources)} record(s), {len(report.approved)} approved")
    for problem in fatal:
        print(f"  ERROR {problem}")
    for problem in warnings:
        print(f"  warn  {problem}")

    if not report.approved:
        print("  note: no approved sources — a production index cannot be built yet")
    return len(fatal), len(warnings) if strict else 0, len(report.approved)


def check_stray_corpus_files() -> int:
    """Indexable files sitting outside the manifest's control."""
    errors = 0
    raw = DATA / "raw"
    if raw.is_dir():
        strays = [
            p for p in raw.rglob("*")
            if p.suffix.lower() in INDEXABLE_SUFFIXES and p.name.lower() != "readme.md"
        ]
        for path in strays:
            print(f"  ERROR untracked corpus file: {path.relative_to(ROOT)} — "
                  "content must be referenced from data/sources.yaml")
            errors += 1
    return errors


def check_published_artifact() -> tuple[int, int]:
    """Returns (errors, chunks_validated).

    The chunk count is the evidence that this check did any work at all —
    see the vacuity guard in main().
    """
    version = corpus.current_version()
    if not version:
        print("artifact: none published (CURRENT is unset)")
        return 0, 0

    directory = corpus.artifact_dir(version)
    if directory is None:
        print(f"  ERROR CURRENT points at {version}, which does not exist")
        return 1, 0

    manifest = corpus.manifest(version)
    if manifest is None:
        print(f"  ERROR artifact {version} has no readable manifest.json")
        return 1, 0

    approved_ids = {s["id"] for s in manifest.get("sources", [])}
    errors = 0
    chunks_path = directory / "chunks.jsonl"
    if not chunks_path.is_file():
        print(f"  ERROR artifact {version} has no chunks.jsonl")
        return 1, 0

    seen = 0
    with chunks_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            seen += 1
            try:
                row = json.loads(line)
            except ValueError:
                print(f"  ERROR chunks.jsonl:{line_no} is not valid JSON")
                errors += 1
                continue
            meta = row.get("metadata", {})
            url = meta.get("url", "")
            host = (urlparse(url).hostname or "") if url else ""
            if host != source_policy.ALLOWED_HOST:
                print(f"  ERROR chunks.jsonl:{line_no} host {host or '(none)'!r} "
                      f"is not {source_policy.ALLOWED_HOST}")
                errors += 1
            if not meta.get("approved"):
                print(f"  ERROR chunks.jsonl:{line_no} chunk is not marked approved")
                errors += 1
            if meta.get("source") not in approved_ids:
                print(f"  ERROR chunks.jsonl:{line_no} source {meta.get('source')!r} "
                      "is not in the artifact manifest")
                errors += 1

    print(f"artifact: {version} — {seen} chunk(s), {manifest.get('documents')} document(s)")
    return errors, seen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument(
        "--release", action="store_true",
        help="also fail when the check validated nothing (see the vacuity guard)",
    )
    args = ap.parse_args()

    print("Corpus source-policy check\n")
    fatal, warned, approved = check_manifest(args.strict)
    print("\nStray corpus files")
    strays = check_stray_corpus_files()
    if not strays:
        print("  none")
    print("\nPublished artifact")
    artifact, chunks = check_published_artifact()

    total = fatal + warned + strays + artifact
    print()

    # --- vacuity guard ------------------------------------------------------
    #
    # This gate used to print "OK — every indexable record traces to an approved
    # ritaj.birzeit.edu source" and exit 0 against an EMPTY set. The statement was
    # vacuously true and operationally meaningless: it had never rejected a real
    # document, so a green run carried no information, and the greenness was
    # actively reassuring. cowork_ritaj/INTAKE.md says as much — "the first real
    # approval is the first time its exit code means anything."
    #
    # A gate that cannot distinguish "everything passed" from "there was nothing
    # to check" is worse than no gate. So the check now reports what it actually
    # validated, and refuses to claim more than that.
    validated_nothing = approved == 0 and chunks == 0

    if total:
        sys.exit(f"FAILED: {total} problem(s).")

    if validated_nothing:
        if args.release:
            sys.exit(
                "FAILED: this check validated NOTHING — 0 approved records and 0 "
                "published chunks.\n"
                "        A release cannot be gated on a check with no subject. "
                "Approve at least one\n"
                "        source (cowork_ritaj/INTAKE.md) and publish an artifact "
                "before cutting a release."
            )
        print("PASSED VACUOUSLY — 0 approved records, 0 published chunks.")
        print("  Nothing was checked, so this result is not evidence of anything.")
        print("  It will exit 1 under --release, which is what the release "
              "checklist runs.")
        return

    print(f"OK — {approved} approved record(s) and {chunks} published chunk(s) "
          "all trace to an approved ritaj.birzeit.edu source.")


if __name__ == "__main__":
    main()
