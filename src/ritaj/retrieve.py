"""Retrieval funnel: hybrid recall (dense + BM25, fused) → rerank → top-k.

Stage 1 (recall): dense search (semantic embeddings) recalls paraphrases and
cross-language matches; BM25 (keyword) nails the exact terms dense search blurs
— course codes, names, fee numbers. They have opposite failure modes, so we run
both and fuse their rankings with Reciprocal Rank Fusion. RRF merges by *rank
position*, not raw score, so it needs no normalization across two very different
scoring scales (cosine distance vs. BM25 relevance). This casts a wide net.

Stage 2 (precision): a cross-encoder reranks the fused candidates by true
(question, chunk) relevance and keeps the best TOP_K (rerank.py).

The public interface is unchanged — retrieve() still returns (chunk, metadata)
pairs — so generate.py and api.py don't need to know how retrieval works.
"""

from . import bm25
from .config import settings
from .embeddings import embed_query
from .rerank import rerank
from .vectorstore import get_collection

# Pull a wider net from each retriever than we ultimately return, so a chunk
# that ranks mid-list in both still has the ranks to surface after fusion.
CANDIDATES = 20
RRF_K = 60  # rank-smoothing constant; 60 is the conventional default.


def _dense(question: str, k: int) -> list[str]:
    """Top-k chunk ids by semantic (embedding) similarity."""
    res = get_collection().query(query_embeddings=[embed_query(question)], n_results=k)
    return res["ids"][0]


def _rrf(rankings: list[list[str]], k: int) -> list[str]:
    """Fuse ranked id lists via Reciprocal Rank Fusion; return top-k ids.

    Each list contributes 1 / (RRF_K + rank) to an id's score (rank starting at
    1), so a chunk that ranks well in *both* lists outscores one found by only a
    single retriever.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=scores.get, reverse=True)[:k]


def retrieve(question: str, k: int | None = None) -> list[tuple[str, dict]]:
    """Return up to k (chunk_text, metadata) pairs, reranked best-first."""
    k = k or settings.top_k
    dense_ids = _dense(question, CANDIDATES)
    sparse_ids = bm25.search(question, CANDIDATES)
    fused = _rrf([dense_ids, sparse_ids], CANDIDATES)
    corpus = bm25.corpus()
    candidates = [corpus[i] for i in fused if i in corpus]
    return rerank(question, candidates, k)
