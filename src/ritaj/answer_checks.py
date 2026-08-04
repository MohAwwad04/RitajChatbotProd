"""Post-answer quality checks that grounding alone doesn't cover.

`grounding.check` asks "is this sentence supported by some source?". Three
failure modes slip past that question, all of which produce an answer that is
individually well-supported and still misleads a student:

  * **Citation coverage** — a factual claim with no `[n]` at all may be perfectly
    true and still leave the student unable to verify it. The release threshold
    is citation precision >= 95%, which is only measurable if coverage is
    measured per answer.
  * **Stale sources** — a fee or deadline quoted from a snapshot taken two terms
    ago is "supported" by that snapshot and wrong today.
  * **Contradictory dates** — when the cited sources' effective windows don't
    overlap, the answer is stitching together two different academic years. Each
    sentence checks out; the answer as a whole doesn't.

These are reported, not enforced: the response carries `checks` so the client can
badge an answer and the admin console can track the rates. Withholding on a
coverage miss would trade a verifiable answer for a refusal, which is the wrong
direction when the underlying facts are supported.
"""

from __future__ import annotations

import re
from datetime import date

from . import source_policy

_CITE = re.compile(r"\[(\d+)\]")
# Dates and years the answer states as fact. Enough to tell whether an answer is
# making date claims at all — the contradiction check only matters when it is.
_DATE_MENTION = re.compile(
    r"\b(20\d{2})\b"
    r"|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
    re.I,
)


def cited_indices(answer: str, n_passages: int) -> list[int]:
    """0-based passage indices cited in `answer`, in first-seen order."""
    seen: list[int] = []
    for match in _CITE.finditer(answer or ""):
        index = int(match.group(1)) - 1
        if 0 <= index < n_passages and index not in seen:
            seen.append(index)
    return seen


def _windows(metas: list[dict]) -> list[tuple[date | None, date | None]]:
    out = []
    for meta in metas:
        start = source_policy._parse_date(meta.get("effective_from"))
        end = source_policy._parse_date(meta.get("effective_to"))
        if start or end:
            out.append((start, end))
    return out


def _disjoint(a: tuple[date | None, date | None], b: tuple[date | None, date | None]) -> bool:
    """True when two effective windows cannot both be in force at any moment."""
    a_start, a_end = a
    b_start, b_end = b
    if a_end and b_start and a_end < b_start:
        return True
    if b_end and a_start and b_end < a_start:
        return True
    return False


def run(
    answer: str,
    passages: list[tuple[str, dict]],
    grounding_report: dict | None = None,
    on: date | None = None,
) -> dict:
    """Coverage, staleness and date-consistency for one finished answer."""
    report = grounding_report or {}
    claims = report.get("n_claims", 0)
    uncited = report.get("uncited_claims", 0)
    coverage = None if not claims else round((claims - uncited) / claims, 3)

    indices = cited_indices(answer, len(passages))
    cited_metas = [passages[i][1] for i in indices]

    stale = [
        meta.get("source")
        for meta in cited_metas
        if meta.get("stale") or source_policy.meta_is_stale(meta, on)
    ]

    windows = _windows(cited_metas)
    contradictory = any(
        _disjoint(windows[i], windows[j])
        for i in range(len(windows))
        for j in range(i + 1, len(windows))
    )
    # Only a problem when the answer actually asserts dates. Two sources from
    # different years can legitimately back a procedural answer that mentions no
    # date at all.
    states_dates = bool(_DATE_MENTION.search(answer or ""))

    return {
        "citation_coverage": coverage,
        "uncited_claims": uncited,
        "cited_sources": len(indices),
        "stale_sources": stale,
        "uses_stale_source": bool(stale),
        "contradictory_dates": bool(contradictory and states_dates),
    }
