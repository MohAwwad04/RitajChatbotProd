#!/usr/bin/env python3
"""Build the vector index — and, with --publish, an immutable corpus artifact.

Why an artifact rather than "rebuild on boot": the index the staging evaluation
ran against must be byte-for-byte the index that answers students, and building
it inside a hosting platform's launch window is what killed the last deployment.
`--publish` writes:

    data/corpus/<version>/
        manifest.json    what went in: source ids, URLs, hashes, counts
        qdrant/          the embedded store, ready to copy into /tmp at boot
        chunks.jsonl     the exact chunk text + metadata, for offline eval
    data/corpus/CURRENT  -> <version>

Version is `YYYYMMDD-<hash>` where the hash covers every approved source's
content hash, so the same inputs produce the same version and any change to any
source produces a new one.

Usage:
    python scripts/build_index.py                    # build into the live store
    python scripts/build_index.py --publish          # + write a versioned artifact
    python scripts/build_index.py --dev              # build the quarantined dev corpus
    python scripts/build_index.py --rehash           # print current content hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import corpus, source_policy  # noqa: E402


def compute_version(sources: list[source_policy.Source]) -> str:
    """Deterministic id for this exact set of source contents."""
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda s: s.id):
        digest.update(source.id.encode())
        digest.update((source.sha256 or "").encode())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{stamp}-{digest.hexdigest()[:10]}"


def rehash() -> int:
    """Print each record's actual content hash so the manifest can be filled in."""
    report = source_policy.load_and_validate(check_content=False)
    if not report.sources:
        print("No records in data/sources.yaml.")
        return 0
    for source in report.sources:
        if not source.has_content():
            print(f"{source.id}: (no content_path — awaiting acquisition)")
            continue
        try:
            print(f"{source.id}: {source_policy.sha256_text(source.text())}")
        except OSError as exc:
            print(f"{source.id}: ERROR {exc}")
    return 0


def publish(version: str, sources: list[source_policy.Source], chunks: int,
            *, unverified: bool = False, provenance_note: str = "") -> Path:
    """Freeze the built store + its manifest into data/corpus/<version>/."""
    from ritaj import vectorstore
    from ritaj.config import settings

    target = corpus.CORPUS_ROOT / version
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    # chunks.jsonl: the exact text/metadata that was indexed. Offline evaluation
    # and any dispute about what the assistant was told read this, not the store.
    rows = vectorstore.get_all()
    with (target / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(
                {"id": row["id"], "text": row["document"], "metadata": row["metadata"]},
                ensure_ascii=False,
            ) + "\n")

    manifest = {
        "version": version,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": len(sources),
        "chunks": chunks,
        "embed_model": settings.embed_model,
        # Set by --unverified. The manifest is the only durable record of what
        # went in, so a corpus that skipped the source policy has to say so here
        # or nothing downstream can.
        "verified": not unverified,
        "provenance_note": provenance_note,
        "sources_sha256": hashlib.sha256(
            "".join(sorted((s.sha256 or "") for s in sources)).encode()
        ).hexdigest(),
        "sources": [
            {
                "id": s.id,
                "canonical_url": s.canonical_url,
                "title": s.title,
                "language": s.language,
                "sha256": s.sha256,
                "fetched_at": s.fetched_at,
                "effective_from": s.effective_from,
                "effective_to": s.effective_to,
                "approved_by": s.approved_by,
            }
            for s in sorted(sources, key=lambda s: s.id)
        ],
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Copy the embedded store so a deploy can restore it without re-embedding.
    if settings.qdrant_path:
        vectorstore.close()  # release the directory lock before copying
        source_dir = Path(settings.qdrant_path)
        if source_dir.is_dir():
            shutil.copytree(source_dir, target / "qdrant")
        else:
            print(f"WARNING: QDRANT_PATH {source_dir} not found; artifact has no store copy")
    else:
        print("NOTE: QDRANT_URL (server) mode — artifact carries chunks.jsonl but no "
              "store copy. Set QDRANT_PATH to publish a restorable artifact.")

    # Point CURRENT at it last: until this line the artifact is incomplete, and
    # a half-written artifact that something already switched to is worse than
    # no artifact at all.
    corpus.CURRENT_POINTER.write_text(version + "\n", encoding="utf-8")
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--publish", action="store_true",
                    help="write an immutable versioned artifact and point CURRENT at it")
    ap.add_argument("--dev", action="store_true",
                    help="build the quarantined development corpus (never production)")
    ap.add_argument("--rehash", action="store_true",
                    help="print each source's actual content hash and exit")
    ap.add_argument(
        "--unverified", metavar="REASON",
        help=(
            "publish the DEVELOPMENT corpus as a real artifact, bypassing the "
            "Ritaj-only source policy. REASON is recorded in the manifest and "
            "surfaced to students. Requires --dev --publish."
        ),
    )
    args = ap.parse_args()

    if args.rehash:
        sys.exit(rehash())

    from ritaj import ingest

    if args.dev:
        print("Building the DEVELOPMENT index from data/quarantine/ ...")
        count = ingest.build_from_directory()
        print(f"Done. {count} chunks indexed.")

        if args.publish and not args.unverified:
            # The default stays a refusal. Publishing this material is a
            # decision with a victim if it goes wrong — a student acting on a
            # fabricated date — so it cannot be reached by adding one more
            # familiar flag to a command someone half-remembers.
            sys.exit(
                "Refusing to publish an artifact from the development corpus.\n\n"
                "Every document in data/quarantine/ failed the Ritaj-only source "
                "policy: off-domain\ncanonical URLs, acquisition from search-engine "
                "listings, and SAMPLE sections that\nare explicitly fabricated "
                "placeholder text. Publishing it means the assistant will cite\n"
                "that material to students as though it were verified.\n\n"
                "If that is genuinely the decision, say so explicitly and it will "
                "be recorded:\n"
                "  --unverified \"<who decided, and why>\"\n"
            )

        if args.publish:
            print()
            print("PUBLISHING UNVERIFIED CONTENT — recorded in the manifest and "
                  "shown to students.")
            print(f"  reason: {args.unverified}")
            version = f"unverified-{date.today().isoformat()}"
            target = publish(version, [], count,
                             unverified=True, provenance_note=args.unverified)
            print(f"  artifact: {target}")
            print()
            print("  Students will see a banner saying the sources are unverified.")
            print("  Replace this the moment one real Ritaj page is approved.")
        return

    report = source_policy.load_and_validate()
    print(report.summary())
    if not report.ok:
        sys.exit("\nSource manifest has fatal problems — nothing was built.")
    if not report.approved:
        sys.exit(
            "\nNo approved sources in data/sources.yaml, so there is nothing to index.\n"
            "This is expected until an authorized Ritaj acquisition path exists —\n"
            "see data/quarantine/README.md. Use --dev to build the development corpus."
        )

    print(f"\nBuilding index from {len(report.approved)} approved source(s) ...")
    count = ingest.build_from_sources(report.approved)
    print(f"Done. {count} chunks indexed.")

    if args.unverified:
        sys.exit("--unverified applies to --dev only; approved sources are already verified.")

    if args.publish:
        version = compute_version(report.approved)
        target = publish(version, report.approved, count)
        print(f"Published corpus {version} -> {target}")


if __name__ == "__main__":
    main()
