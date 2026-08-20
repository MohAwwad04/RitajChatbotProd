"""Startup initialization — runs on a background thread, never blocks the port.

Two ways the vector store can become answerable:

  1. **Restore** (production). `scripts/build_index.py --publish` produced an
     immutable corpus artifact containing an already-embedded Qdrant directory.
     Boot copies it into writable storage and opens it. No model load, no
     embedding — seconds instead of minutes, and the index that was evaluated in
     staging is byte-for-byte the index serving students.
  2. **Build** (development, and a deliberate fallback). Embed the approved
     sources in-process. This is what used to run on every Hugging Face boot,
     inside the launch window, ahead of the web server — which is how the
     deployment ended up dying at `Launch timed out`.

Restore is tried first and build only happens when explicitly permitted, so a
production host can never silently fall into the slow path.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from . import corpus, readiness, vectorstore
from .config import settings

log = logging.getLogger("ritaj.bootstrap")


def _store_populated() -> bool:
    """True when the collection READS ACTUALLY GO TO already holds chunks.

    Was `collection_exists(settings.collection)` — the plain name. In remote
    mode reads go through `QDRANT_COLLECTION_ALIAS`, and the whole point of the
    alias is that the underlying collection is named `ritaj_<version>` and
    changes on every publish. So a correctly published corpus looked EMPTY here,
    boot raised `CORPUS_UNAVAILABLE`, and the service refused to serve an index
    it was successfully connected to. Confirmed against the live cluster:
    `collection_exists` does resolve an alias, so the fix is simply to ask about
    the name that is actually read.
    """
    try:
        target = vectorstore.read_collection()
        return (
            vectorstore.client().collection_exists(target)
            and vectorstore.count() > 0
        )
    except Exception as exc:  # noqa: BLE001 — store may not exist yet; that's a no
        log.info("vector store not readable yet: %s", exc)
        return False


def restore_artifact() -> dict | None:
    """Copy the published corpus artifact into QDRANT_PATH. None if unavailable.

    Only meaningful in embedded mode: with a remote Qdrant server the index lives
    in the server, and shipping a directory into it is not a thing you can do.
    """
    if not settings.qdrant_path:
        return None
    source = corpus.artifact_dir()
    if source is None:
        return None
    qdrant_src = source / "qdrant"
    if not qdrant_src.is_dir():
        log.warning("corpus artifact %s has no qdrant/ directory", source)
        return None

    target = Path(settings.qdrant_path)
    if target.exists() and any(target.iterdir()):
        # Already restored (a warm container restart). Re-copying would race the
        # open store for its lock and gains nothing.
        log.info("qdrant storage at %s already populated; skipping restore", target)
        return {"restored": False, "reason": "already-populated"}

    started = time.monotonic()
    # Close first: in embedded mode Qdrant holds a lock on the directory, and the
    # restore must own it exclusively.
    vectorstore.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(qdrant_src, target, dirs_exist_ok=True)
    log.info("restored corpus %s into %s in %.2fs",
             corpus.current_version(), target, time.monotonic() - started)
    return {"restored": True, "seconds": round(time.monotonic() - started, 2)}


def initialize(*, allow_build: bool | None = None) -> dict:
    """Make the service answerable. Returns detail for the readiness snapshot.

    Raises on failure — `readiness.start_background_init` turns that into the
    `failed` state, and chat then reports NOT_READY rather than pretending.
    """
    if allow_build is None:
        allow_build = settings.allow_index_build_on_boot

    detail: dict = {"corpus_version": corpus.current_version()}

    restored = restore_artifact()
    if restored:
        detail["restore"] = restored

    if not _store_populated():
        if not allow_build:
            raise RuntimeError(
                "No corpus artifact to serve and index building is disabled on this "
                "host. Publish an artifact with `python scripts/build_index.py "
                "--publish` and redeploy, or set ALLOW_INDEX_BUILD_ON_BOOT=1."
            )
        log.warning("no populated store — building the index in-process (slow path)")
        from .ingest import build_index  # noqa: PLC0415 — heavy import, only on this path

        started = time.monotonic()
        chunks = build_index()
        detail["built"] = {"chunks": chunks, "seconds": round(time.monotonic() - started, 2)}
        if chunks == 0:
            raise RuntimeError("index build produced 0 chunks — no approved sources found")

    detail["chunks"] = vectorstore.count()

    # Prove retrieval actually works before claiming ready. A store that opens
    # but returns nothing is exactly the failure /ready exists to catch, and it
    # also warms the embedder + BM25 index so the first student doesn't pay for it.
    started = time.monotonic()
    from .retrieve import retrieve  # noqa: PLC0415 — pulls in the models

    probe = retrieve("registration", k=1)
    detail["warmup_retrieval_seconds"] = round(time.monotonic() - started, 2)
    if not probe:
        raise RuntimeError("retrieval warm-up returned no passages")
    readiness.mark("retrieval_ready")

    detail["llm"] = _check_llm_config()
    return detail


def _check_llm_config() -> dict:
    """Validate LLM configuration without spending a token on it.

    A live call would cost quota on every restart and make readiness depend on a
    third party's uptime. What we can check for free is that the deployment was
    actually configured — the failure this catches is a Space deployed with the
    provider secret missing, which otherwise looks fine until the first question.
    """
    configured = bool(settings.llm_base_url and settings.llm_model)
    hosted = not any(
        h in settings.llm_base_url for h in ("localhost", "127.0.0.1", "0.0.0.0")
    )
    if hosted and not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not set for a hosted LLM endpoint")
    if not configured:
        raise RuntimeError("LLM_BASE_URL / LLM_MODEL are not configured")
    return {"model": settings.llm_model, "hosted": hosted}
