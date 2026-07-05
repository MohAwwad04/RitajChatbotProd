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

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import settings

def _make_client() -> QdrantClient:
    # Embedded on-disk mode (QDRANT_PATH) for single-container deploys; otherwise
    # an http Qdrant server. The ingest pre-process and the API server share the
    # same path within one container run, so the built index is visible to both.
    if settings.qdrant_path:
        return QdrantClient(path=settings.qdrant_path)
    return QdrantClient(url=settings.qdrant_url)


_client = _make_client()
_NS = uuid.UUID("a3f1c0de-0000-4000-8000-000000000000")  # fixed namespace for ids


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NS, chunk_id))


def reset(dim: int) -> None:
    """Drop and recreate the collection (used at index build)."""
    # delete + create rather than the deprecated recreate_collection().
    if _client.collection_exists(settings.collection):
        _client.delete_collection(settings.collection)
    _client.create_collection(
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
    _client.upsert(settings.collection, points=points)


def query(embedding: list[float], k: int) -> list[tuple[str, float]]:
    """Top-k as (chunk_id, cosine_distance), nearest first."""
    res = _client.query_points(
        settings.collection, query=embedding, limit=k, with_payload=True
    ).points
    return [(p.payload["chunk_id"], 1.0 - p.score) for p in res]


def get_all() -> list[dict]:
    """Every stored chunk: {id, document, metadata, embedding}.

    Pages through scroll so we never silently cap the corpus at one page.
    """
    out = []
    offset = None
    while True:
        points, offset = _client.scroll(
            settings.collection, limit=1000, offset=offset,
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


def count() -> int:
    return _client.count(settings.collection).count
