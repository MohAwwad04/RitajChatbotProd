"""About-the-makers intent — a fixed credit answer (with team photos).

This is a deterministic special case, not a RAG answer: "who built this site?" has
no document in the corpus, and the response is a hand-written credit, so it
short-circuits before retrieval/LLM (like guardrails.check_scope). The team photos
are served from src/ritaj/static/team (mounted at /static in api.py).
"""

import re

from . import arabic

# Matches "who made/built/created this site/project/bot" and the Arabic
# equivalents. Run over arabic.normalize_light(message), so Arabic patterns are
# written in their normalized form (أ/إ→ا, ة→ه, ى→ي, diacritics dropped).
_ABOUT = re.compile(
    # --- English ---
    r"\bwho\s+(?:made|built|created|develop(?:ed)?|design(?:ed)?|program(?:med)?|did|wrote)\b"
    r"|\bwho(?:'?s| is| are)\s+(?:behind|the\s+(?:developer|maker|creator|author|team))\b"
    r"|\bmade\s+(?:this|you)\b|\bbuilt\s+(?:this|you)\b"
    # --- Arabic (normalized) ---
    r"|(?:من|مين)\s+(?:عمل|صمم|صنع|انشا|بني|طور|برمج|كتب|اخرج|عملك|صممك|طورك)"
    r"|من\s+وراء"
    r"|من\s+(?:هو|هم)?\s*(?:مطور|مبرمج|صاحب|مصمم|صانع)"
    r"|(?:اسماء?|من\s+هم)\s+الطلاب",
    re.I,
)

# Any Arabic character → reply in Arabic, else English.
_HAS_ARABIC = re.compile(r"[؀-ۿ]")

RESPONSE_AR = (
    "هذا عمل الطلاب المبدعين محمدخير عواد و محمد شماسنة، في مساق نظم المعلومات "
    "القائمة على النصوص باشراف الدكتور احمد شواهنة."
)
RESPONSE_EN = (
    "This site was built by the talented students Mohammad Awwad and Mohammad "
    "Shamasneh, for the Text-based Information Systems course, under the "
    "supervision of Dr. Ahmad Shawahneh."
)

# Team photos, served from /static/team (see api.py StaticFiles mount).
IMAGES = [
    {"url": "/static/team/awwad.jpg", "caption": "محمدخير عواد · Mohammad Awwad"},
    {"url": "/static/team/shamasneh.jpg", "caption": "محمد شماسنة · Mohammad Shamasneh"},
]


def match(message: str) -> bool:
    """True if `message` is asking who made the site/project."""
    return bool(_ABOUT.search(arabic.normalize_light(message)))


def response(message: str) -> str:
    """The credit text, in the language of the question."""
    return RESPONSE_AR if _HAS_ARABIC.search(message) else RESPONSE_EN
