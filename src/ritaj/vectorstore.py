"""ChromaDB wrapper.

PersistentClient writes to disk (CHROMA_PATH) so the index survives restarts.
We use cosine distance because the e5 embeddings are normalized.

Note: Chroma is dense-only — it has no BM25/keyword search. The hybrid-search
half of the plan (a BM25 sidecar fused via RRF) is a later addition and lives
outside this module.
"""

import chromadb

from .config import settings

_client = chromadb.PersistentClient(path=settings.chroma_path)


def get_collection():
    return _client.get_or_create_collection(
        settings.collection,
        metadata={"hnsw:space": "cosine"},
    )
