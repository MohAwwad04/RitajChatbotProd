"""Smoke tests that run without downloading models or starting servers.

The chunker is pure logic, so we can verify it in CI cheaply. Full retrieval/
generation tests (which need the embedder + a running LLM) come later and grow
into the golden-set eval harness (plan section 13).
"""

from ritaj import arabic
from ritaj.bm25 import _tokenize
from ritaj.ingest import chunk_text
from ritaj.retrieve import _rrf


def test_chunking_produces_overlapping_windows():
    text = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(text, target=400, overlap=60)

    assert len(chunks) > 1
    # Each chunk (except possibly the last) holds `target` words.
    assert len(chunks[0].split()) == 400
    # Consecutive chunks overlap: the tail of chunk 0 reappears in chunk 1.
    assert chunks[0].split()[-1] in chunks[1].split()


def test_chunking_empty_text():
    assert chunk_text("") == []


def test_rrf_rewards_agreement_across_lists():
    # "b" is found by both retrievers; "a" and "c" each by only one.
    dense = ["a", "b"]
    sparse = ["c", "b"]
    fused = _rrf([dense, sparse], k=3)

    # Scoring in both lists, "b" outranks the single-list "a" and "c".
    assert fused[0] == "b"
    assert set(fused) == {"a", "b", "c"}


def test_rrf_keeps_items_found_by_only_one_list():
    fused = _rrf([["x", "y"], ["z"]], k=10)
    assert set(fused) == {"x", "y", "z"}


def test_arabic_normalizes_letter_and_diacritic_variants():
    assert arabic.normalize_light("أحذف") == "احذف"  # alef-hamza -> bare alef
    assert arabic.normalize_light("مُقَرَّر") == "مقرر"  # diacritics stripped
    assert arabic.normalize_light("كــتاب") == "كتاب"  # tatweel removed
    assert arabic.normalize_light("٢٠٢٥") == "2025"  # arabic-indic digits


def test_arabic_strips_definite_article_when_word_long_enough():
    assert arabic.strip_article("المقرر") == "مقرر"
    assert arabic.strip_article("الى") == "الى"  # too short to strip


def test_arabic_normalization_is_noop_on_english():
    assert arabic.normalize_light("Add/Drop Fall 2025") == "Add/Drop Fall 2025"


def test_tokenizer_collapses_arabic_variants_to_match():
    # article + question mark all gone; the bare form is what gets indexed
    assert _tokenize("كيف أحذف المقرر؟") == ["كيف", "احذف", "مقرر"]


def test_tokenizer_lowercases_and_drops_punctuation_in_english():
    assert _tokenize("How do I drop a course in Ritaj?") == [
        "how", "do", "i", "drop", "a", "course", "in", "ritaj"
    ]
