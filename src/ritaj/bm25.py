"""BM25 sparse-retrieval sidecar.

Exact-term matches (course codes, names, fee numbers) that dense embeddings blur
over need a keyword index running alongside the vector search. We keep a BM25
sidecar over the very same chunks stored in the vector store, query both, and
fuse the two rankings in retrieve.py (RRF). (Qdrant can do sparse vectors
natively too — folding BM25 into the store is a possible future simplification,
see future.md.)

There is no second copy of the corpus to keep in sync: build_index() populates
the vector store, and this module reads the chunks back out of it (vectorstore.
get_all). The index is built lazily and cached, mirroring the lazy model load in
embeddings.py — fine for a serve-after-offline-build workflow (rebuild the index,
restart the API).

Tokenization normalizes Arabic before matching (arabic.py): a literal keyword
index treats مقرر and المقرر as different words, so without this the BM25 half of
the funnel is nearly blind in Arabic. The same normalization runs on documents
(at index build) and queries (at search), so both meet in the same canonical
form. English passes through unchanged.
"""

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from . import arabic, vectorstore

# \w+ splits on whitespace AND punctuation (so the ؟ in مقرر؟ no longer sticks),
# and matches Arabic letters/digits as word characters.
_TOKEN = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    text = arabic.normalize_light(text).lower()
    return [arabic.strip_article(t) for t in _TOKEN.findall(text)]


class _Index:
    """A BM25 index plus the id/doc/meta it was built from."""

    def __init__(self, ids: list[str], docs: list[str], metas: list[dict]):
        self.ids = ids
        self.docs = docs
        self.metas = metas
        self.bm25 = BM25Okapi([_tokenize(d) for d in docs])

    def search_scored(self, question: str, k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(_tokenize(question))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [(self.ids[i], float(scores[i])) for i in ranked[:k]]

    def search(self, question: str, k: int) -> list[str]:
        return [cid for cid, _ in self.search_scored(question, k)]


@lru_cache(maxsize=1)
def _index() -> _Index:
    rows = vectorstore.get_all()  # every chunk: id, document, metadata
    return _Index(
        [r["id"] for r in rows],
        [r["document"] for r in rows],
        [r["metadata"] for r in rows],
    )


def search(question: str, k: int) -> list[str]:
    """Return up to k chunk ids ranked by BM25 keyword relevance."""
    return _index().search(question, k)


def search_scored(question: str, k: int) -> list[tuple[str, float]]:
    """Like search(), but return (chunk_id, bm25_score) pairs for inspection."""
    return _index().search_scored(question, k)


def corpus() -> dict[str, tuple[str, dict]]:
    """id -> (chunk_text, metadata) for every indexed chunk.

    The single source of truth retrieve.py maps fused ids back through, so dense
    and sparse results resolve to identical chunk text/metadata.
    """
    idx = _index()
    return {i: (d, m) for i, d, m in zip(idx.ids, idx.docs, idx.metas)}
