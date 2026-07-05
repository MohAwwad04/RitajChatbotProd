"""Ingestion pipeline: load -> chunk -> embed -> upsert.

This is the simplest honest version of plan section 6. It deliberately uses a
plain sliding-window chunker; structure-aware chunking and Arabic normalization
come later. Metadata (source/title) is attached now because the answer layer
needs it to cite sources.
"""

from pathlib import Path

from pypdf import PdfReader

from .embeddings import embed_passages
from .vectorstore import get_collection

SUPPORTED = {".pdf", ".txt", ".md"}


def read_document(path: Path) -> str:
    """Extract plain text from a PDF or text/markdown file."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, target: int = 400, overlap: int = 60) -> list[str]:
    """Split text into overlapping word windows (~500 tokens each).

    Overlap keeps context from leaking across boundaries so a fact split
    between two chunks is still retrievable.
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    step = max(1, target - overlap)
    for i in range(0, len(words), step):
        chunks.append(" ".join(words[i : i + target]))
        if i + target >= len(words):
            break
    return chunks


def build_index(data_dir: str = "data/raw") -> int:
    """(Re)build the vector index from every supported file in data_dir.

    Uses upsert so re-running updates existing chunks instead of duplicating.
    Returns the number of chunks indexed.
    """
    collection = get_collection()
    total = 0
    for path in sorted(Path(data_dir).rglob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        chunks = chunk_text(read_document(path))
        if not chunks:
            continue
        ids = [f"{path.stem}-{i}" for i in range(len(chunks))]
        metas = [
            {"source": path.name, "title": path.stem.replace("_", " "), "path": str(path)}
            for _ in chunks
        ]
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embed_passages(chunks),
            metadatas=metas,
        )
        print(f"  indexed {len(chunks):>3} chunks from {path.name}")
        total += len(chunks)
    return total
