"""Multilingual embeddings.

We use the e5 family, which expects different prefixes for the stored text
("passage: ") and the search text ("query: "). Getting these prefixes right
materially improves Arabic/English retrieval quality, so we keep the two paths
separate instead of a single embed() function.

The model is loaded lazily so importing this module (e.g. in tests) doesn't
trigger a multi-GB download until you actually embed something.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from . import arabic
from .config import settings


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(settings.embed_model)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed documents/chunks for storage."""
    prefixed = [f"passage: {arabic.normalize_light(t)}" for t in texts]
    return _model().encode(prefixed, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a user question for search."""
    text = arabic.normalize_light(text)
    return _model().encode([f"query: {text}"], normalize_embeddings=True)[0].tolist()
