"""Cross-encoder reranker — the precision stage of the retrieval funnel.

Hybrid retrieval (retrieve.py) is tuned for recall: it casts a wide net so the
right chunk lands *somewhere* in the candidate list, but its ordering is rough
because dense and BM25 both score the query and a chunk in isolation.

A cross-encoder fixes the ordering. It feeds the question and one chunk through
the model *together* ([question] [SEP] [chunk]) so every token of the query can
attend to every token of the chunk, and emits a single relevance score. That is
far more accurate than comparing two independently-computed vectors — but it is
also too slow to run over the whole corpus, so it only runs over the ~20 fused
candidates and trims them to the top TOP_K, best first.

The model is loaded lazily (like the embedder) so importing this module doesn't
trigger a download until something is actually reranked.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder


@lru_cache(maxsize=1)
def _model() -> "CrossEncoder":
    # Deferred like embeddings._model: importing sentence_transformers is itself
    # expensive, and it must not sit between process start and the port binding.
    from sentence_transformers import CrossEncoder  # noqa: PLC0415

    return CrossEncoder(settings.rerank_model, revision=settings.rerank_revision)


def rerank_scored(
    question: str, passages: list[tuple[str, dict]], k: int
) -> list[tuple[tuple[str, dict], float]]:
    """Reorder passages by relevance; keep the top k as (passage, score) pairs."""
    if not passages:
        return []
    scores = _model().predict([[question, doc] for doc, _ in passages])
    ranked = sorted(zip(passages, scores), key=lambda pair: pair[1], reverse=True)
    return [(passage, float(score)) for passage, score in ranked[:k]]


def rerank(
    question: str, passages: list[tuple[str, dict]], k: int
) -> list[tuple[str, dict]]:
    """Reorder passages by true (question, chunk) relevance; keep the top k."""
    return [passage for passage, _ in rerank_scored(question, passages, k)]
