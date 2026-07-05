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

from . import bm25, runtime_config, vectorstore
from .embeddings import embed_query
from .rerank import rerank, rerank_scored

# These are tunable from the /admin calibration tab (runtime_config):
#   candidates — width of the net each recall stage pulls before fusion
#   rrf_k      — rank-smoothing constant in Reciprocal Rank Fusion
#   top_k      — how many reranked chunks become the final answer context


def _dense(question: str, k: int) -> list[str]:
    """Top-k chunk ids by semantic (embedding) similarity."""
    return [cid for cid, _ in vectorstore.query(embed_query(question), k)]


def _rrf(rankings: list[list[str]], k: int) -> list[str]:
    """Fuse ranked id lists via Reciprocal Rank Fusion; return top-k ids.

    Each list contributes 1 / (rrf_k + rank) to an id's score (rank starting at
    1), so a chunk that ranks well in *both* lists outscores one found by only a
    single retriever.
    """
    rrf_k = runtime_config.get("rrf_k")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores, key=scores.get, reverse=True)[:k]


def retrieve(question: str, k: int | None = None) -> list[tuple[str, dict]]:
    """Return up to k (chunk_text, metadata) pairs, reranked best-first."""
    k = k or runtime_config.get("top_k")
    candidates = runtime_config.get("candidates")
    dense_ids = _dense(question, candidates)
    sparse_ids = bm25.search(question, candidates)
    fused = _rrf([dense_ids, sparse_ids], candidates)
    corpus = bm25.corpus()
    chunks = [corpus[i] for i in fused if i in corpus]
    return rerank(question, chunks, k)


# How many candidates each recall stage exposes in the trace (the funnel pulls
# CANDIDATES=20 internally; showing all 20 per stage would swamp the UI).
TRACE_SHOW = 8


def trace(question: str, k: int | None = None) -> dict:
    """Run the same funnel as retrieve(), but capture every stage for the UI.

    Returns each stage's ranked chunks with the score that stage ranks by, so
    you can watch a chunk climb or fall from dense -> BM25 -> fusion -> rerank.
    """
    k = k or runtime_config.get("top_k")
    candidates = runtime_config.get("candidates")
    rrf_k = runtime_config.get("rrf_k")
    corpus = bm25.corpus()

    def view(cid: str, **extra) -> dict:
        text, meta = corpus.get(cid, ("", {}))
        return {
            "id": cid,
            "title": meta.get("title"),
            "source": meta.get("source"),
            "text": text[:180],
            **extra,
        }

    # Stage 1 — dense (semantic) recall.
    dense_hits = vectorstore.query(embed_query(question), candidates)
    dense_ids = [cid for cid, _ in dense_hits]
    dense_dist = [dist for _, dist in dense_hits]
    dense_rank = {cid: r for r, cid in enumerate(dense_ids, 1)}

    # Stage 2 — sparse (BM25 keyword) recall.
    sparse = bm25.search_scored(question, candidates)
    sparse_ids = [cid for cid, _ in sparse]
    sparse_rank = {cid: r for r, cid in enumerate(sparse_ids, 1)}

    # Stage 3 — Reciprocal Rank Fusion of the two rankings.
    fused_ids = _rrf([dense_ids, sparse_ids], candidates)
    rrf_score: dict[str, float] = {}
    for ranking in (dense_ids, sparse_ids):
        for r, cid in enumerate(ranking, 1):
            rrf_score[cid] = rrf_score.get(cid, 0.0) + 1.0 / (rrf_k + r)

    # Stage 4 — cross-encoder rerank of the fused candidates -> final top-k.
    pairs = [(corpus[cid], cid) for cid in fused_ids if cid in corpus]
    id_of = {id(passage): cid for passage, cid in pairs}
    reranked = rerank_scored(question, [p for p, _ in pairs], k)
    final = [(id_of[id(passage)], score) for passage, score in reranked]

    stages = [
        {
            "name": "1 · Dense recall — e5 cosine",
            "metric": "cos dist",
            "note": f"semantic search over all chunks; lower = closer. Top {candidates} kept.",
            "items": [
                view(cid, score=round(dense_dist[i], 3))
                for i, cid in enumerate(dense_ids[:TRACE_SHOW])
            ],
        },
        {
            "name": "2 · Sparse recall — BM25",
            "metric": "bm25",
            "note": "exact-keyword match (codes, fees) that embeddings blur; higher = better.",
            "items": [view(cid, score=round(sc, 2)) for cid, sc in sparse[:TRACE_SHOW]],
        },
        {
            "name": "3 · RRF fusion",
            "metric": "rrf",
            "note": "merge the two rankings by rank position; a chunk in both wins.",
            "items": [
                view(
                    cid,
                    score=round(rrf_score[cid], 4),
                    dense_rank=dense_rank.get(cid),
                    sparse_rank=sparse_rank.get(cid),
                )
                for cid in fused_ids[:TRACE_SHOW]
            ],
        },
        {
            "name": f"4 · Rerank → top {k}",
            "metric": "relevance",
            "final": True,
            "note": "cross-encoder scores (question, chunk) jointly; this is the final context.",
            "items": [view(cid, score=round(score, 3)) for cid, score in final],
        },
    ]
    return {"k": k, "stages": stages, "final_ids": [cid for cid, _ in final]}
