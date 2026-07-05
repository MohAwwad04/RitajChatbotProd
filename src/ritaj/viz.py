"""Project the embedding space down to something you can look at.

The stored e5 vectors are 1024-dimensional, which is invisible. We fit a PCA
basis on the corpus once (the 3 directions of greatest variance) and reuse that
same basis to place both the stored chunks and any live query into 3 axes. So
"close together in the plot" approximates "close together in the 1024-D space
the retriever actually searches".

The basis is cached: a query must be projected with the exact same axes the
chunks were drawn with, or the picture would be meaningless.
"""

import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import runtime_config, vectorstore
from .embeddings import embed_query
from .ingest import _split_sections, chunk_markdown, chunk_text, read_document, SUPPORTED

_DATA_DIR = Path("data/raw")


@lru_cache(maxsize=1)
def _fit():
    """Pull every stored vector and fit a 3-component PCA basis."""
    rows = vectorstore.get_all()
    if len(rows) < 3:
        # Need ≥3 vectors for a 3-D PCA; return an empty/short basis safely.
        dim = len(rows[0]["embedding"]) if rows else 1
        return np.zeros(dim), np.zeros((3, dim)), [], [0.0, 0.0, 0.0]

    X = np.asarray([r["embedding"] for r in rows], dtype=float)  # (n, 1024)

    mean = X.mean(axis=0)
    # Right singular vectors of the centered matrix == principal axes.
    _, sing, Vt = np.linalg.svd(X - mean, full_matrices=False)
    components = Vt[:3]  # (3, 1024)
    coords = (X - mean) @ components.T  # (n, 3)

    total = var_sum if (var_sum := (sing**2).sum()) else 1.0
    explained = ((sing[:3] ** 2) / total).tolist()

    points = [
        {
            "id": r["id"],
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "z": float(coords[i, 2]),
            "title": r["metadata"].get("title"),
            "source": r["metadata"].get("source"),
            "text": r["document"][:300],
        }
        for i, r in enumerate(rows)
    ]
    return mean, components, points, explained


def points() -> dict:
    """The stored chunks as 3D points, plus how much variance the axes keep."""
    _, _, pts, explained = _fit()
    return {"points": pts, "explained_variance": explained}


def project_query(text: str, k: int = 3) -> dict:
    """Embed a query the same way retrieval does, then place it in the plot.

    `neighbors` are the chunks the store returns for this query in the real
    1024-D space (cosine), so you can compare what's *actually* nearest against
    what merely looks nearest after the lossy projection to 3D.
    """
    mean, components, _, _ = _fit()
    q = np.asarray(embed_query(text), dtype=float)
    coord = (q - mean) @ components.T

    neighbors = [
        {"id": cid, "distance": dist}
        for cid, dist in vectorstore.query(q.tolist(), k)
    ]
    return {
        "x": float(coord[0]),
        "y": float(coord[1]),
        "z": float(coord[2]),
        "text": text,
        "neighbors": neighbors,
    }


_LIST_RE = re.compile(r"(\d+[.)]|[-*+])\s")


def chunking() -> dict:
    """Show how each raw document is split into structure-aware chunks.

    Re-runs the exact chunker used at index time (chunk_markdown) over data/raw,
    so this view matches what's actually stored. For each chunk we surface its
    "Title > Section" header, word count, and whether it kept a table or list
    whole -- the things structure-aware chunking does differently from a blind
    word window.
    """
    target = runtime_config.get("chunk_target")
    overlap = runtime_config.get("chunk_overlap")
    chunker = chunk_markdown if runtime_config.get("chunk_strategy") == "structure" else chunk_text

    documents = []
    for path in sorted(_DATA_DIR.rglob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        text = read_document(path)
        title, sections = _split_sections(text)

        chunks = []
        for c in chunker(text, target=target, overlap=overlap):
            header, _, body = c.partition("\n\n")
            if not body:
                header, body = "", c
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            chunks.append({
                "header": header,
                "words": len(c.split()),
                "has_table": sum(ln.startswith("|") for ln in lines) >= 2,
                "has_list": sum(bool(_LIST_RE.match(ln)) for ln in lines) >= 2,
                "text": body[:700],
            })

        documents.append({
            "source": path.name,
            "title": title,
            "words": len(text.split()),
            "sections": len(sections),
            "chunks": chunks,
        })

    return {
        "documents": documents,
        "total_docs": len(documents),
        "total_chunks": sum(len(d["chunks"]) for d in documents),
    }
