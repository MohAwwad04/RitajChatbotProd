"""Arabic text normalization.

Arabic writes the same word several ways — the definite article «الـ» glued on
(مقرر vs المقرر), interchangeable letter forms (أ إ آ ا, ى/ي, ة/ه), optional
diacritics (tashkeel), the decorative tatweel ـ, and Arabic-Indic digits
(٢٠٢٥ vs 2025). Byte-for-byte these differ, so a literal keyword index (BM25)
treats them as unrelated words and misses the match.

We map all those forms to one canonical form, applied identically to documents
and queries so both sides meet in the middle. English contains none of these
characters, so every function here is a no-op on it.

Two strengths, for two different consumers:
- normalize_light(): letters, diacritics, tatweel, digits. Safe to feed the
  embedder (embeddings.py), which already handles Arabic but benefits from a
  consistent input on both the passage and query sides.
- strip_article(): token-level removal of a leading «الـ». Aggressive; used by
  the BM25 tokenizer (bm25.py), where exact-token matching needs it most.
"""

import re

# Diacritics (tashkeel), superscript alef, and assorted Quranic marks.
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"  # ـ decorative stretching char

# Letter-form unifications: variant -> canonical.
_LETTERS = str.maketrans(
    {
        "آ": "ا",  # آ alef madda       -> ا
        "أ": "ا",  # أ alef hamza-above -> ا
        "إ": "ا",  # إ alef hamza-below -> ا
        "ٱ": "ا",  # ٱ alef wasla       -> ا
        "ى": "ي",  # ى alef maqsura     -> ي
        "ی": "ي",  # ی farsi yeh        -> ي
        "ة": "ه",  # ة ta marbuta       -> ه
        "ؤ": "و",  # ؤ waw with hamza   -> و
        "ئ": "ي",  # ئ ya with hamza    -> ي
    }
)

# Arabic-Indic (٠-٩) and extended/Persian (۰-۹) digits -> ASCII 0-9.
_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩"
    "۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

_ARTICLE = "ال"  # ال


def normalize_light(text: str) -> str:
    """Canonical letters/diacritics/digits. Safe for the embedder; no-op on English."""
    text = _DIACRITICS.sub("", text)
    text = text.replace(_TATWEEL, "")
    text = text.translate(_LETTERS)
    text = text.translate(_DIGITS)
    return text


def strip_article(token: str) -> str:
    """Drop a leading «الـ» when enough word remains (keyword recall: المقرر≈مقرر).

    Guarded by a length check so short words that merely start with ا+ل aren't
    gutted into a meaningless stub.
    """
    if token.startswith(_ARTICLE) and len(token) > 4:
        return token[2:]
    return token
