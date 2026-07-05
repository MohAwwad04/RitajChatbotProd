"""Ingestion pipeline: load -> chunk -> embed -> upsert.

This is the simplest honest version of plan section 6. It deliberately uses a
plain sliding-window chunker; structure-aware chunking and Arabic normalization
come later. Metadata (source/title) is attached now because the answer layer
needs it to cite sources.
"""

import re
from pathlib import Path

from pypdf import PdfReader

from . import runtime_config, vectorstore
from .embeddings import embed_passages

SUPPORTED = {".pdf", ".txt", ".md"}

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def read_document(path: Path) -> str:
    """Extract plain text from a PDF or text/markdown file."""
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, target: int = 120, overlap: int = 20) -> list[str]:
    """Split text into overlapping word windows.

    120 words (~15% overlap) is the empirical sweet spot from
    scripts/eval_chunk_size.py: large enough to keep a fact whole, small enough
    that each chunk's embedding stays focused on one idea so queries rank the
    right chunk first. Bigger windows blur multi-fact documents; much smaller
    ones split facts across chunks and hurt top-1 recall.

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


def _split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split Markdown into (title, [(heading, body), ...]) by # / ## headings.

    The H1 title is pulled out as document-wide context (it goes into every
    chunk's header, not its own chunk). Any preamble between the title and the
    first ## section (e.g. a `> SOURCE:` provenance block) is folded into the
    first section rather than becoming a contentless chunk of its own.
    """
    title = ""
    pre: list[str] = []
    sections: list[list] = []  # [heading, body_lines]
    cur: list | None = None
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            level, htext = len(m.group(1)), m.group(2).strip()
            if level == 1:
                title = htext
            else:
                cur = [htext, []]
                sections.append(cur)
        elif cur is None:
            pre.append(line)
        else:
            cur[1].append(line)
    if sections:
        sections[0][1] = pre + sections[0][1]
    elif pre:
        sections = [["", pre]]
    return title, [(h, "\n".join(b).strip()) for h, b in sections]


def _blocks(body: str) -> list[str]:
    """Split a section body into atomic blocks on blank lines.

    A Markdown table or a numbered/bulleted list has no internal blank lines, so
    each stays a single block here — which is what keeps us from splitting one
    mid-row or mid-step.
    """
    return [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]


_LIST_MARKER = re.compile(r"(\d+[.)]|[-*+])\s")


def _is_atomic(block: str) -> bool:
    """True if the block is a table or list that must never be split.

    Counts ≥2 marker/pipe lines, OR a block whose first line is already a
    table/list marker (so a list with wrapped continuation lines that don't
    repeat the marker still counts as one indivisible block).
    """
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    first_is_marker = lines[0].startswith("|") or bool(_LIST_MARKER.match(lines[0]))
    tableish = sum(ln.startswith("|") for ln in lines) >= 2
    listish = sum(bool(_LIST_MARKER.match(ln)) for ln in lines) >= 2
    return first_is_marker or tableish or listish


def _pack(blocks: list[str], target: int, overlap: int) -> list[str]:
    """Greedily pack whole blocks into chunks up to `target` words.

    A block larger than target is word-windowed only if it is plain prose; a
    table/list block is emitted intact even when it exceeds the target.
    """
    out: list[str] = []
    cur: list[str] = []
    cur_n = 0

    def flush():
        nonlocal cur, cur_n
        if cur:
            out.append("\n\n".join(cur))
            cur, cur_n = [], 0

    for blk in blocks:
        n = len(blk.split())
        if n > target:
            flush()
            out.extend([blk] if _is_atomic(blk) else chunk_text(blk, target, overlap))
            continue
        if cur and cur_n + n > target:
            flush()
        cur.append(blk)
        cur_n += n
    flush()
    return out


def chunk_markdown(text: str, target: int = 120, overlap: int = 20) -> list[str]:
    """Structure-aware chunking (PLAN 6.3).

    Splits on Markdown headings instead of a blind word window, keeps tables and
    step-by-step lists intact, and prepends a "Title > Section" header to every
    chunk so the heading context is embedded and citable. Falls back to plain
    word-windowing for headingless text (e.g. extracted PDFs).
    """
    title, sections = _split_sections(text)
    chunks: list[str] = []
    for heading, body in sections:
        if not body:
            continue
        header = " > ".join(p for p in (title, heading) if p)
        for piece in _pack(_blocks(body), target, overlap):
            chunks.append(f"{header}\n\n{piece}" if header else piece)
    return chunks


def build_index(data_dir: str = "data/raw") -> int:
    """(Re)build the vector index from every supported file in data_dir.

    Recreates the collection from scratch, so re-running is clean (no stale
    chunks left from a previous chunking). Returns the number of chunks indexed.
    """
    # Chunking is tunable from /admin (runtime_config): strategy + size + overlap.
    target = runtime_config.get("chunk_target")
    overlap = runtime_config.get("chunk_overlap")
    strategy = runtime_config.get("chunk_strategy")
    chunker = chunk_markdown if strategy == "structure" else chunk_text

    root = Path(data_dir)
    docs = []  # (id, chunk_text, metadata) across all files
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        chunks = chunker(read_document(path), target=target, overlap=overlap)
        meta = {"source": path.name, "title": path.stem.replace("_", " "), "path": str(path)}
        # id from the full relative path, so same-named files in different
        # folders (or with different extensions) don't collide and overwrite.
        rel = str(path.relative_to(root))
        for i, chunk in enumerate(chunks):
            docs.append((f"{rel}-{i}", chunk, meta))
        if chunks:
            print(f"  indexed {len(chunks):>3} chunks from {path.name}")

    if not docs:
        return 0
    ids, texts, metas = zip(*docs)
    embeddings = embed_passages(list(texts))
    vectorstore.reset(dim=len(embeddings[0]))
    vectorstore.upsert(list(ids), list(texts), embeddings, list(metas))

    # The BM25 and PCA caches read the store; invalidate them so a same-process
    # rebuild (or a script that builds then queries) doesn't serve stale data.
    from . import bm25, viz
    bm25._index.cache_clear()
    viz._fit.cache_clear()
    return len(docs)
