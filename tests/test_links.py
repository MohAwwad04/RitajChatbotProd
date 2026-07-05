"""Model-free tests for the deterministic page-link layer (links.py).

The link map is loaded from data/links.yaml, but these tests don't depend on its
exact contents: they monkeypatch links._load_map with a small fixed map so the
selection logic (citation parsing, dedupe, cap, fallback, no-hallucination) is
what's under test, not the live YAML. The cache is cleared so the patch takes.
"""

import pytest

from ritaj import links

# A tiny fixture map: one doc with two pages, one with a single page, and (by
# omission) an "unmapped" doc that appears in passages but not here.
FIXMAP = {
    "tuition_and_fees.md": [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"},
    ],
    "ritaj_portal_and_it.md": [
        {"label": "Ritaj Portal", "url": "https://ritaj.birzeit.edu/"},
        {"label": "IT Services", "url": "https://www.birzeit.edu/en/it-services"},
    ],
    "library_services.md": [
        {"label": "BZU Library", "url": "https://www.birzeit.edu/en/study/bzu-library"},
    ],
    "many_links.md": [
        {"label": "L1", "url": "https://example.edu/1"},
        {"label": "L2", "url": "https://example.edu/2"},
        {"label": "L3", "url": "https://example.edu/3"},
        {"label": "L4", "url": "https://example.edu/4"},
    ],
}


@pytest.fixture
def fixed_map(monkeypatch):
    monkeypatch.setattr(links, "_load_map", lambda: FIXMAP)
    return FIXMAP


def _p(*sources):
    """Build a passages list (chunk, meta) with the given source filenames."""
    return [(f"chunk for {s}", {"source": s, "title": s}) for s in sources]


def test_returns_url_for_the_cited_doc(fixed_map):
    # [2] cites the tuition doc -> its verified URL, not the top-1 doc's.
    passages = _p("ritaj_portal_and_it.md", "tuition_and_fees.md")
    out = links.links_for(passages, "Most programs are JD 125 per credit hour [2].")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_uses_best_ranked_cited_source_only(fixed_map):
    # Cited as [2] then [1], but only the best-RANKED cited source contributes:
    # passages are reranked best-first, so passage 0 (tuition) wins — not every
    # cited doc, and not citation order.
    passages = _p("tuition_and_fees.md", "library_services.md")
    out = links.links_for(passages, "See [2] and also [1].")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_skips_top_cited_doc_without_links(fixed_map):
    # Best-ranked cited doc (passage 0) is unmapped; fall through to the next
    # cited source that actually has links, rather than returning nothing.
    passages = _p("does_not_exist.md", "tuition_and_fees.md")
    out = links.links_for(passages, "See [1] and [2].")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_dedupes_repeated_doc_and_repeated_url(fixed_map):
    # The same doc cited twice (and a doc whose URL repeats) yields one link each.
    passages = _p("tuition_and_fees.md", "tuition_and_fees.md")
    out = links.links_for(passages, "JD 125 [1]. Again JD 125 [1][2].")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_only_best_source_links_not_tangential_docs(fixed_map):
    # Several docs cited, but only the best-ranked cited source (passage 0,
    # ritaj_portal_and_it.md) contributes — tuition/library are NOT surfaced.
    passages = _p(
        "ritaj_portal_and_it.md",  # 2 urls — passage 0, the primary source
        "tuition_and_fees.md",     # 1 url — tangential, must be ignored
        "library_services.md",     # 1 url — tangential, must be ignored
    )
    out = links.links_for(passages, "[1][2][3]")
    assert [link["url"] for link in out] == [
        "https://ritaj.birzeit.edu/",
        "https://www.birzeit.edu/en/it-services",
    ]
    assert len(out) <= links.MAX_LINKS


def test_caps_single_source_at_max_links(fixed_map):
    # One source with more than MAX_LINKS URLs is still capped.
    passages = _p("many_links.md")
    out = links.links_for(passages, "see [1]")
    assert len(out) == links.MAX_LINKS == 3
    assert [link["url"] for link in out] == [
        "https://example.edu/1", "https://example.edu/2", "https://example.edu/3",
    ]


def test_unmapped_doc_contributes_no_link(fixed_map):
    # A cited doc absent from the map yields nothing (no fabricated URL).
    passages = _p("does_not_exist.md")
    assert links.links_for(passages, "Here it is [1].") == []


def test_falls_back_to_top1_when_no_citation(fixed_map):
    # No [n] markers at all -> use the single best-retrieved (top-1) doc's links.
    passages = _p("tuition_and_fees.md", "library_services.md")
    out = links.links_for(passages, "An answer with no citation markers.")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_out_of_range_citation_is_ignored_then_falls_back(fixed_map):
    # [9] with only 2 passages is dropped; with no valid citation left, fall back.
    passages = _p("tuition_and_fees.md", "library_services.md")
    out = links.links_for(passages, "See [9].")
    assert out == [
        {"label": "Tuition Fees", "url": "https://www.birzeit.edu/en/admissions/tuition-fees-0"}
    ]


def test_never_returns_url_absent_from_map(fixed_map):
    # Property: every URL returned exists in the map (no hallucination path).
    allowed = {e["url"] for entries in FIXMAP.values() for e in entries}
    passages = _p("tuition_and_fees.md", "ritaj_portal_and_it.md", "library_services.md")
    out = links.links_for(passages, "Mix it up [3][1][2] and [2] again.")
    assert out  # something came back
    assert all(link["url"] in allowed for link in out)


def test_empty_passages_returns_empty(fixed_map):
    assert links.links_for([], "[1]") == []


def test_no_map_returns_empty(monkeypatch):
    # A missing/broken links.yaml degrades to no links, never an error.
    monkeypatch.setattr(links, "_load_map", lambda: {})
    assert links.links_for(_p("tuition_and_fees.md"), "JD 125 [1].") == []


def test_real_yaml_loads_and_maps_a_known_doc():
    # Smoke-check the actual data/links.yaml: it loads and the tuition doc maps to
    # the tuition-fees page (this is the acceptance-criteria doc).
    links._load_map.cache_clear()
    real = links._load_map()
    assert "tuition_and_fees.md" in real
    urls = [e["url"] for e in real["tuition_and_fees.md"]]
    assert "https://www.birzeit.edu/en/admissions/tuition-fees-0" in urls
    # Every entry is well-formed (label + url present).
    for entries in real.values():
        for e in entries:
            assert e.get("label") and e.get("url")
