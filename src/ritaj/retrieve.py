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

import re
from datetime import date, datetime, timezone

from . import bm25, readiness, runtime_config, vectorstore
from .embeddings import embed_query
from .rerank import rerank, rerank_scored

# These are tunable from the /admin calibration tab (runtime_config):
#   candidates      — width of the net each recall stage pulls before fusion
#   rrf_k           — rank-smoothing constant in Reciprocal Rank Fusion
#   top_k           — how many reranked chunks become the final answer context
#   min_relevance   — abstention floor: below this, a chunk is not context
#   language_filter — whether to prefer sources in the question's language

# A four-digit year, or an academic year written either way round
# ("2025/2026", "2025-2026"). Used to decide whether a student is deliberately
# asking about a past term, in which case expired records stop being noise and
# become the answer.
_YEAR = re.compile(r"\b(20\d{2})(?:\s*[/–-]\s*(20\d{2}))?\b")
_ARABIC = re.compile(r"[؀-ۿ]")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def query_language(question: str) -> str:
    """'ar' or 'en' — which language's sources should be preferred.

    Any Arabic script at all means Arabic: students routinely mix a Latin course
    code or an English module name into an Arabic question ("كيف أسجل COMP2310؟"),
    and that must not flip the question to English and hide the Arabic sources.
    """
    return "ar" if _ARABIC.search(question) else "en"


def years_mentioned(question: str) -> set[str]:
    """Years the question names explicitly, e.g. {'2025', '2026'}."""
    found: set[str] = set()
    for match in _YEAR.finditer(question):
        found.update(g for g in match.groups() if g)
    return found


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


def _visible(meta: dict) -> bool:
    """Chunks that may be shown to a student at all.

    A production index only contains approved records, but a development index
    (data/quarantine) does not, and the two must never be confused at answer
    time. This is the last gate before text reaches a prompt.
    """
    return meta.get("visibility", "public") == "public"


def _effective_penalty(meta: dict, asked_years: set[str], on: date) -> float:
    """0.0 for a currently-effective source; a positive penalty for an expired one.

    Expired records stay searchable — a student asking "what were last year's
    dates?" deserves an answer — but the default must prefer what is in force.
    A rank penalty rather than a hard filter, because the alternative is
    answering a question about 2024 with 2026's calendar, or refusing it.
    """
    effective_to = meta.get("effective_to") or ""
    if not effective_to:
        return 0.0
    try:
        end = date.fromisoformat(effective_to[:10])
    except ValueError:
        return 0.0
    if end >= on:
        return 0.0
    # Expired. If the question names a year inside this record's window, the
    # student asked for it — no penalty.
    starts = (meta.get("effective_from") or "")[:4]
    window_years = {starts, effective_to[:4]} - {""}
    if asked_years & window_years:
        return 0.0
    return runtime_config.get("expired_penalty")


def _language_penalty(meta: dict, wanted: str) -> float:
    """Small penalty for answering in the other language's sources.

    Not a filter: Ritaj publishes plenty of pages in one language only, and
    refusing to use an English page for an Arabic question would abstain on
    questions the corpus can actually answer.
    """
    language = meta.get("language") or ""
    if not language or language == wanted:
        return 0.0
    return runtime_config.get("language_penalty")


def _dedupe(scored: list[tuple[tuple[str, dict], float]]) -> list[tuple[tuple[str, dict], float]]:
    """Drop later chunks from a section already represented, best-first.

    Structure-aware chunking gives consecutive chunks the same "Title > Section"
    header, so a long section can occupy every slot in the context with near-
    identical text — crowding out the other document that actually holds the
    rest of the answer. Keeping the best chunk per section widens what the model
    sees without widening top_k (which costs tokens on a metered provider).
    """
    seen: set[tuple[str, str]] = set()
    out = []
    for (text, meta), score in scored:
        # First line of a structure-aware chunk is its "Title > Section" header.
        section = text.split("\n", 1)[0][:120]
        key = (meta.get("source", ""), section)
        if key in seen:
            continue
        seen.add(key)
        out.append(((text, meta), score))
    return out


def retrieve_scored(
    question: str, k: int | None = None, *, on: date | None = None
) -> list[tuple[tuple[str, dict], float]]:
    """The full funnel, returning (passage, adjusted relevance) best-first.

    Order matters: recall wide, rerank the wide set, then apply metadata
    adjustments and abstention to the reranked scores. Filtering before the
    reranker would discard candidates on metadata the reranker might have shown
    to be irrelevant anyway, and would make the abstention threshold mean
    different things for different questions.
    """
    k = k or runtime_config.get("top_k")
    candidates = runtime_config.get("candidates")
    on = on or _today()

    dense_ids = _dense(question, candidates)
    sparse_ids = bm25.search(question, candidates)
    fused = _rrf([dense_ids, sparse_ids], candidates)
    corpus = bm25.corpus()
    chunks = [corpus[i] for i in fused if i in corpus and _visible(corpus[i][1])]

    # Rerank the whole candidate pool, not just k: the adjustments below can
    # reorder, so cutting to k first would throw away the chunk that wins.
    reranked = rerank_scored(question, chunks, len(chunks))

    wanted_language = query_language(question)
    asked_years = years_mentioned(question)
    adjusted = [
        (
            passage,
            score
            - _effective_penalty(passage[1], asked_years, on)
            - _language_penalty(passage[1], wanted_language),
        )
        for passage, score in reranked
    ]
    adjusted.sort(key=lambda pair: pair[1], reverse=True)

    deduped = _dedupe(adjusted)

    # Abstention: a chunk below the floor is not evidence. Returning it anyway
    # is how a confident answer gets built on a passage that merely shares
    # vocabulary with the question.
    floor = runtime_config.get("min_relevance")
    kept = [(passage, score) for passage, score in deduped if score >= floor][:k]

    readiness.mark("first_retrieval")
    return kept


def retrieve(question: str, k: int | None = None, *, on: date | None = None
             ) -> list[tuple[str, dict]]:
    """Return up to k (chunk_text, metadata) pairs, reranked best-first.

    Empty when nothing clears the relevance floor — the caller must treat that
    as "no source supports an answer", not as "retrieval failed".
    """
    return [passage for passage, _ in retrieve_scored(question, k, on=on)]


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
