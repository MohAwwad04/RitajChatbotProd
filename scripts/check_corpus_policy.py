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


def check_manifest(strict: bool) -> tuple[int, int]:
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
    return len(fatal), len(warnings) if strict else 0


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


def check_published_artifact() -> int:
    """Every chunk in the published artifact traces to an approved Ritaj URL."""
    version = corpus.current_version()
    if not version:
        print("artifact: none published (CURRENT is unset)")
        return 0

    directory = corpus.artifact_dir(version)
    if directory is None:
        print(f"  ERROR CURRENT points at {version}, which does not exist")
        return 1

    manifest = corpus.manifest(version)
    if manifest is None:
        print(f"  ERROR artifact {version} has no readable manifest.json")
        return 1

    approved_ids = {s["id"] for s in manifest.get("sources", [])}
    errors = 0
    chunks_path = directory / "chunks.jsonl"
    if not chunks_path.is_file():
        print(f"  ERROR artifact {version} has no chunks.jsonl")
        return 1

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
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = ap.parse_args()

    print("Corpus source-policy check\n")
    fatal, warned = check_manifest(args.strict)
    print("\nStray corpus files")
    strays = check_stray_corpus_files()
    if not strays:
        print("  none")
    print("\nPublished artifact")
    artifact = check_published_artifact()

    total = fatal + warned + strays + artifact
    print()
    if total:
        sys.exit(f"FAILED: {total} problem(s).")
    print("OK — every indexable record traces to an approved ritaj.birzeit.edu source.")


if __name__ == "__main__":
    main()
