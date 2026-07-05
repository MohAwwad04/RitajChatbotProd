"""Deterministic source -> page-link lookup (citation-aware).

The LLM never emits URLs (that would risk hallucinated links). Instead, once an
answer is generated we know exactly which source documents it cited — the answer
carries inline `[n]` markers, and `n` indexes the same passage list we built the
prompt from. This module maps those cited passages to their source document's
verified page URL(s) using a curated map (`data/links.yaml`) that lives OUTSIDE
the indexed text, so it never affects retrieval.

Selection (links_for):
  1. Parse the `[n]` markers actually present in the final answer.
  2. Take the SINGLE best-ranked cited source: passages are reranked best-first,
     so the lowest cited index is the doc the question is really about. We walk
     cited passages in rank order and use the first one that has mapped links.
  3. Return that source's URL(s), deduped, capped at MAX_LINKS.
  4. If the answer cited nothing, fall back to the top-1 retrieved doc's link.
Only the primary source contributes links — a schedule answer that also cites the
IT-helpdesk doc shouldn't surface "IT Services". Any doc not in the map
contributes no link (no hallucination path: every URL we return came from the map).

Loading is best-effort: a missing or malformed links.yaml just yields no links,
mirroring the runtime writers elsewhere that no-op on OSError.
"""

import re
from functools import lru_cache
from pathlib import Path

# data/links.yaml at the project root, resolved independently of the cwd
# (src/ritaj/links.py -> parents[2] is the repo root), same way api.py locates
# the built portal.
_LINKS_PATH = Path(__file__).resolve().parents[2] / "data" / "links.yaml"

# Cap on links returned per answer — a short, scannable row, not a link dump.
MAX_LINKS = 3

# Matches inline citation markers like [1], [2] in the generated answer.
_CITE = re.compile(r"\[(\d+)\]")


@lru_cache(maxsize=1)
def _load_map() -> dict[str, list[dict]]:
    """Load the source -> [links] map once. Best-effort: {} on any failure.

    Cached for the process; call _load_map.cache_clear() after editing the file
    (e.g. a future admin reload), the way ingest invalidates its caches.
    """
    try:
        import yaml  # optional dep; absence just disables links

        data = yaml.safe_load(_LINKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # Keep only well-formed entries (a label + url); ignore anything else so a
    # half-edited file degrades gracefully instead of raising.
    clean: dict[str, list[dict]] = {}
    for source, entries in data.items():
        if not isinstance(entries, list):
            continue
        good = [
            {"label": e["label"], "url": e["url"]}
            for e in entries
            if isinstance(e, dict) and e.get("label") and e.get("url")
        ]
        if good:
            clean[source] = good
    return clean


def _cited_indices(answer: str, n_passages: int) -> list[int]:
    """0-based passage indices cited in `answer`, in first-seen order.

    Drops out-of-range markers (a `[9]` with only 6 passages) so a stray citation
    can't index past the list.
    """
    seen: list[int] = []
    for m in _CITE.finditer(answer or ""):
        i = int(m.group(1)) - 1
        if 0 <= i < n_passages and i not in seen:
            seen.append(i)
    return seen


def links_for(passages: list[tuple[str, dict]], answer: str) -> list[dict]:
    """Return up to MAX_LINKS {label, url} for the docs the answer cited.

    `passages` is the reranked (chunk, metadata) list used to build the prompt,
    so passage index i corresponds to the `[i+1]` marker. Falls back to the
    top-1 retrieved doc when the answer cited nothing. Returns [] if there are no
    passages or the map yields nothing.
    """
    if not passages:
        return []
    link_map = _load_map()
    if not link_map:
        return []

    indices = _cited_indices(answer, len(passages))
    if not indices:
        # No citation to key on — fall back to the single best-retrieved doc.
        indices = [0]

    # Only the most relevant cited source contributes links. Passages are reranked
    # best-first, so walk cited passages in rank order and use the first one that
    # actually has mapped links; ignore the rest (tangential citations to lower-
    # ranked docs would otherwise surface off-topic pages).
    out: list[dict] = []
    seen_urls: set[str] = set()
    for i in sorted(indices):
        source = passages[i][1].get("source")
        entries = link_map.get(source)
        if not entries:
            continue
        for entry in entries:
            url = entry["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            out.append({"label": entry["label"], "url": url})
            if len(out) >= MAX_LINKS:
                break
        return out  # one source only — the best-ranked cited doc with links
    return out
