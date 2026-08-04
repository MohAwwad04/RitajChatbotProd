"""Multilingual embeddings.

We use the e5 family, which expects different prefixes for the stored text
("passage: ") and the search text ("query: "). Getting these prefixes right
materially improves Arabic/English retrieval quality, so we keep the two paths
separate instead of a single embed() function.

The model is loaded lazily so importing this module (e.g. in tests) doesn't
trigger a multi-GB download until you actually embed something.

The *library* import is deferred too, not just the model. `import
sentence_transformers` alone costs ~2.8 s of the ~3.7 s it took to import
ritaj.api — and that time is spent before uvicorn binds the port, which is
precisely the window the platform was timing out on. Nothing on the liveness
path needs a model, so nothing on it should pay to import one.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

from . import arabic
from .config import settings

if TYPE_CHECKING:  # type-checkers get the real symbol; runtime never imports it
    from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    return SentenceTransformer(settings.embed_model, revision=settings.embed_revision)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed documents/chunks for storage."""
    prefixed = [f"passage: {arabic.normalize_light(t)}" for t in texts]
    return _model().encode(prefixed, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    """Embed a user question for search."""
    text = arabic.normalize_light(text)
    return _model().encode([f"query: {text}"], normalize_embeddings=True)[0].tolist()
