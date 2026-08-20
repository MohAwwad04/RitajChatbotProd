"""Qdrant vector store — the single seam the rest of the code talks to.

We keep a small, store-agnostic surface (reset / upsert / query / get_all) so no
Qdrant types leak into ingest/retrieve/viz. Cosine space, because the e5 vectors
are normalized.

Qdrant point ids must be uint/UUID, but our chunk ids are strings like
"tuition_and_fees-0". We derive a stable UUID5 from the string for the point id
(so re-indexing the same chunk overwrites in place, like the old upsert) and keep
the original id, the chunk text, and metadata in the payload.

`query()` returns a cosine *distance* (1 - similarity) to match what the UI and
trace already expect (lower = closer), independent of the backend.
"""

import uuid
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from . import config
from .config import settings


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    """The Qdrant handle, opened on first use.

    Lazy, not module-level, for two reasons. Embedded mode (QDRANT_PATH) takes a
    lock on the storage directory, so opening at import time would race the
    startup restore that copies the published corpus artifact into that
    directory. And importing this module — which api.py does transitively — must
    never be what makes /live fail.

    The mode is asked for explicitly (config.qdrant_mode) rather than inferred
    from which setting is non-empty. Inference meant a deployment carrying both
    a cloud URL and a stale QDRANT_PATH ran embedded against an empty directory
    and looked healthy: identical, from the outside, to an empty corpus.
    """
    problems = config.qdrant_problems()
    if problems:
        # Fail loudly at the seam rather than connecting to the wrong store.
        # The messages never contain the URL or the key — see config._scheme_of.
        raise RuntimeError("Qdrant configuration: " + "; ".join(problems))

    if config.qdrant_mode() == "embedded":
        return QdrantClient(path=settings.qdrant_path)
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        # Qdrant Cloud terminates TLS; an unbounded default timeout turns a
        # cluster that is suspended (free tier, after a week idle) into a
        # request that hangs instead of one that fails.
        timeout=int(settings.qdrant_timeout_seconds),
        https=settings.qdrant_url.startswith("https://"),
    )


def read_collection() -> str:
    """The collection queries should read.

    The alias when one is configured, otherwise the plain collection name. Read
    paths go through here so a corpus swap is a pointer move, not a redeploy.
    """
    return settings.qdrant_alias or settings.collection


def close() -> None:
    """Release the storage lock (embedded mode) so the directory can be replaced."""
    if client.cache_info().currsize:
        try:
            client().close()
        except Exception:  # noqa: BLE001 — best effort; we're tearing down anyway
            pass
        client.cache_clear()


_NS = uuid.UUID("a3f1c0de-0000-4000-8000-000000000000")  # fixed namespace for ids


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NS, chunk_id))


def reset(dim: int) -> None:
    """Drop and recreate the collection (used at index build)."""
    # delete + create rather than the deprecated recreate_collection().
    if client().collection_exists(settings.collection):
        client().delete_collection(settings.collection)
    client().create_collection(
        settings.collection,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def upsert(
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    points = [
        PointStruct(
            id=_point_id(cid),
            vector=emb,
            payload={"chunk_id": cid, "document": doc, **meta},
        )
        for cid, doc, emb, meta in zip(ids, documents, embeddings, metadatas)
    ]
    client().upsert(settings.collection, points=points)


def query(embedding: list[float], k: int) -> list[tuple[str, float]]:
    """Top-k as (chunk_id, cosine_distance), nearest first."""
    res = client().query_points(
        read_collection(), query=embedding, limit=k, with_payload=True
    ).points
    return [(p.payload["chunk_id"], 1.0 - p.score) for p in res]


def get_all() -> list[dict]:
    """Every stored chunk: {id, document, metadata, embedding}.

    Pages through scroll so we never silently cap the corpus at one page.
    """
    out = []
    offset = None
    while True:
        points, offset = client().scroll(
            read_collection(), limit=1000, offset=offset,
            with_payload=True, with_vectors=True,
        )
        for p in points:
            payload = dict(p.payload)
            out.append({
                "id": payload.pop("chunk_id"),
                "document": payload.pop("document"),
                "metadata": payload,  # whatever's left: title, source, path
                "embedding": p.vector,
            })
        if offset is None:
            break
    return out


def collection_ready() -> bool:
    """True when the collection queries read actually exists and is reachable.

    Deliberately NOT folded into get_all()/count() as a "return empty" fallback.
    Those are on the retrieval path, where an absent collection and an empty one
    must stay distinguishable: pointing at the wrong cluster would otherwise look
    exactly like a corpus that has not been built, which is the failure mode the
    explicit QDRANT_MODE work exists to prevent.

    This is for read-only display surfaces that should say "nothing indexed"
    instead of returning 500 — which is what /admin/points did on a fresh
    deployment, i.e. at exactly the moment an operator goes looking.
    """
    try:
        return client().collection_exists(read_collection())
    except Exception:  # noqa: BLE001 — unreachable store is "not ready" here
        return False


def count() -> int:
    return client().count(read_collection()).count


# --- Versioned publication ---------------------------------------------------
#
# `reset()` above drops and recreates the collection in place. That is fine for
# an embedded store rebuilt on boot, and unacceptable against a shared remote
# one: it deletes the corpus students are querying, and if the rebuild then
# fails — a bad snapshot, an OOM, an expired key — the service is left with no
# corpus at all and no way back except re-running the job that just failed.
#
# The publication path below never touches the live collection. It builds
# `ritaj_<version>` alongside whatever is serving, verifies the count, and only
# then moves the alias. The previous collection stays until someone deletes it,
# so rollback is another alias move rather than a rebuild.

def versioned_name(version: str) -> str:
    """Collection name for a corpus version. Must be a valid Qdrant identifier."""
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in version)
    if not safe:
        raise ValueError("corpus version is empty after sanitisation")
    return f"{settings.collection}_{safe}"


def create_versioned(version: str, dim: int) -> str:
    """Create (or recreate) the collection for one corpus version. Returns its name.

    Recreating a *version* collection is safe in a way that recreating the live
    one is not: nothing reads it until the alias moves, so a failed or repeated
    build discards only its own work.
    """
    name = versioned_name(version)
    if client().collection_exists(name):
        client().delete_collection(name)
    client().create_collection(
        name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
    )
    return name


def upsert_into(
    name: str,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    batch_size: int = 256,
) -> int:
    """Upsert into a named collection in bounded batches. Returns points written.

    Batched because Qdrant Cloud's free tier is a 0.5 vCPU / 1 GB node: one
    request carrying the whole corpus is how a small node returns 413 or simply
    stops responding mid-import, leaving a partial collection that looks fine.
    """
    written = 0
    for start in range(0, len(ids), batch_size):
        stop = start + batch_size
        points = [
            PointStruct(
                id=_point_id(cid),
                vector=emb,
                payload={"chunk_id": cid, "document": doc, **meta},
            )
            for cid, doc, emb, meta in zip(
                ids[start:stop], documents[start:stop],
                embeddings[start:stop], metadatas[start:stop],
            )
        ]
        client().upsert(name, points=points, wait=True)
        written += len(points)
    return written


def verify_count(name: str, expected: int) -> None:
    """Refuse to publish a collection that does not hold what was sent.

    The failure this catches is a partial import that returned no error — the
    alias would then point at a corpus missing arbitrary documents, and the only
    symptom is the assistant abstaining on questions it should answer, which
    reads as a retrieval-quality problem rather than a deployment one.
    """
    actual = client().count(name).count
    if actual != expected:
        raise RuntimeError(
            f"collection {name!r} holds {actual} points, expected {expected} — not publishing"
        )


def current_alias_target() -> str | None:
    """Which collection the read alias points at, or None if it is unset."""
    alias = settings.qdrant_alias
    if not alias:
        return None
    try:
        for record in client().get_aliases().aliases:
            if record.alias_name == alias:
                return record.collection_name
    except Exception:  # noqa: BLE001 — an unsupported/unreachable store is "unknown"
        return None
    return None


def publish(name: str) -> str | None:
    """Point the read alias at `name`, atomically. Returns the previous target.

    Qdrant applies an alias operation list atomically, so delete+create in one
    call is a switch, not a gap: there is no instant at which the alias resolves
    to nothing. Doing it as two calls would leave exactly that window, and it
    would land during the busiest moment of a deploy.
    """
    alias = settings.qdrant_alias
    if not alias:
        raise RuntimeError(
            "QDRANT_COLLECTION_ALIAS is not set — nothing to publish to. Set it "
            "so reads go through an alias, or the swap is a redeploy instead."
        )
    if not client().collection_exists(name):
        raise RuntimeError(f"cannot publish {name!r}: it does not exist")

    previous = current_alias_target()
    from qdrant_client.models import (  # noqa: PLC0415 — keep the import local
        AliasOperations,
        CreateAlias,
        CreateAliasOperation,
        DeleteAlias,
        DeleteAliasOperation,
    )

    operations: list[AliasOperations] = []
    if previous is not None:
        operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)))
    operations.append(
        CreateAliasOperation(
            create_alias=CreateAlias(collection_name=name, alias_name=alias)
        )
    )
    client().update_collection_aliases(change_aliases_operations=operations)
    return previous
