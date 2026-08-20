"""Corpus artifact identity — which knowledge build is answering questions.

Phase 2 makes the index an *immutable, versioned artifact* rather than something
rebuilt from whatever happens to be in `data/raw/` at boot. That only means
anything if the running service can name the version it loaded, so:

  * `scripts/build_index.py` writes `data/corpus/<version>/manifest.json` and
    points `data/corpus/CURRENT` at it;
  * this module reads that pointer;
  * `/ready`, the release manifest and the admin console all report it.

Everything here is best-effort and read-only: a missing or malformed artifact
yields None rather than raising, because the corpus version is diagnostic
metadata, not something answering should depend on.
"""

from __future__ import annotations

import json
from pathlib import Path

# data/corpus/ at the repo root, resolved independently of the cwd
# (src/ritaj/corpus.py -> parents[2] is the repo root), like links.py does.
CORPUS_ROOT = Path(__file__).resolve().parents[2] / "data" / "corpus"
CURRENT_POINTER = CORPUS_ROOT / "CURRENT"


def current_version() -> str | None:
    """The corpus version this deployment should serve, or None if unbuilt."""
    try:
        version = CURRENT_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return version or None


def artifact_dir(version: str | None = None) -> Path | None:
    """Directory holding the given (default: current) corpus artifact."""
    version = version or current_version()
    if not version:
        return None
    path = CORPUS_ROOT / version
    return path if path.is_dir() else None


def manifest(version: str | None = None) -> dict | None:
    """The corpus build manifest: chunk counts, checksums, source ids, dates."""
    directory = artifact_dir(version)
    if directory is None:
        return None
    try:
        return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary() -> dict:
    """Small, safe-to-expose description of the loaded corpus.

    Shown by /ready and the release manifest. Deliberately omits file paths and
    raw source text — it is a public health surface.
    """
    version = current_version()
    man = manifest(version) or {}
    return {
        "version": version,
        "built_at": man.get("built_at"),
        "documents": man.get("documents"),
        "chunks": man.get("chunks"),
        "sources_sha256": man.get("sources_sha256"),
        # Whether every indexed source passed the Ritaj-only source policy.
        # False means the operator deliberately published material that did not
        # — off-domain, unverified acquisition, or carrying SAMPLE placeholder
        # text. That is a decision an operator is allowed to make, and it is not
        # a decision a student should have to discover from a wrong answer, so
        # it travels with the corpus and both clients surface it.
        #
        # Absent in an older manifest, which predates any unverified publish, so
        # the safe reading of a missing value is True.
        "verified": bool(man.get("verified", True)),
        "provenance_note": man.get("provenance_note") or "",
    }
