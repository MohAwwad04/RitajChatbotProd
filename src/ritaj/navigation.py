"""Deterministic navigation — the model may name an action, never a destination.

The rule this module exists to enforce (ADR-002): a plausible answer must not be
able to move the student's browser. So generation and navigation are separate
paths, and they meet only at an **action id**:

    question -> resolver -> action id -> registry -> reviewed URL

The LLM's largest possible contribution is choosing an id that a human already
approved. It cannot emit a URL, cannot invent a path, and cannot reach a host
other than `ritaj.birzeit.edu`. If an id does not exist in the registry, nothing
happens.

Resolution is deterministic and ordered (roadmap §6.2):

    1. exact intent/alias match, Arabic or English
    2. a reviewed action referenced by the retrieved sources, above a threshold
    3. (optional, disabled) a model tool-call returning an action id only
    4. otherwise: no navigation, just source links

Every destination is validated twice — here, and again in the extension before
`chrome.tabs.create()` (chrome-extension/navigation.js). Server-side validation
alone would mean a compromised or spoofed backend could steer the browser, which
is precisely the authority this design withholds from the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlunparse

from . import arabic

ALLOWED_HOST = "ritaj.birzeit.edu"
ALLOWED_SCHEME = "https"

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "navigation.yaml"

# Confidence below which a retrieval-derived action is not offered. Deliberately
# high: navigation precision is held to 100% on the release set because a wrong
# destination changes browser state, not just what the student is told.
DEFAULT_MIN_CONFIDENCE = 0.75


@dataclass
class Action:
    """One reviewed navigation destination."""

    id: str
    label_ar: str
    label_en: str
    destination: str
    auth_required: bool = False
    requires_confirmation: bool = True
    enabled: bool = True
    intents_ar: list[str] = field(default_factory=list)
    intents_en: list[str] = field(default_factory=list)
    safe_query_keys: list[str] = field(default_factory=list)
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    source_ids: list[str] = field(default_factory=list)
    owner: str = ""
    approved_by: str = ""

    def label(self, locale: str = "en") -> str:
        return self.label_ar if locale == "ar" else self.label_en

    def payload(self, locale: str = "en") -> dict:
        """The `navigation` SSE event's action object."""
        return {
            "id": self.id,
            "label": self.label(locale),
            "url": self.destination,
            "auth_required": self.auth_required,
            "requires_confirmation": self.requires_confirmation,
        }


# --- URL policy --------------------------------------------------------------
def _structural_problem(url: str) -> str | None:
    """Why `url` can never be a destination, independent of the registry."""
    if not url or not isinstance(url, str):
        return "empty"
    # A scheme-relative URL ("//host/path") inherits the page's scheme and is a
    # classic way to smuggle a different host past a naive check.
    if url.startswith("//"):
        return "scheme-relative"
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return f"unparseable ({exc})"
    if parsed.scheme != ALLOWED_SCHEME:
        return f"scheme must be https, got {parsed.scheme or '(none)'!r}"
    if parsed.username or parsed.password:
        return "embedded credentials"
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_HOST:
        # Covers www.birzeit.edu, sibling subdomains, suffix tricks
        # (ritaj.birzeit.edu.attacker.test) and punycode homoglyphs, because
        # nothing but an exact match is accepted.
        return f"host must be exactly {ALLOWED_HOST}, got {host or '(none)'!r}"
    if parsed.port not in (None, 443):
        return f"non-standard port {parsed.port}"
    if parsed.fragment:
        return "fragments are not allowed"
    if ".." in parsed.path:
        return "path traversal"
    # A URL is opened by a browser, so anything that could be re-parsed as a
    # different target is refused rather than normalised.
    if any(ch in url for ch in ("\\", "\n", "\r", "\t", " ")):
        return "contains whitespace or a backslash"
    return None


def canonical(url: str) -> str:
    """Normalized form used for registry comparison (drops trailing-slash noise)."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, (parsed.hostname or "").lower(), path,
                       "", parsed.query, ""))


def validate_destination(url: str, action: Action | None = None) -> str | None:
    """The URL if it may be opened, else None.

    With `action`, the URL must be that action's registered destination (same
    path, and only query keys the action declares safe). Without one, it must
    match *some* registered action — an unregistered path on the right host is
    still not a destination this product will open.
    """
    if _structural_problem(url) is not None:
        return None

    parsed = urlparse(url)
    query_keys = {k for k, _ in parse_qsl(parsed.query, keep_blank_values=True)}

    candidates = [action] if action is not None else list(load_registry().values())
    for candidate in candidates:
        if candidate is None or not candidate.enabled:
            continue
        registered = urlparse(candidate.destination)
        if canonical(url).split("?")[0] != canonical(candidate.destination).split("?")[0]:
            continue
        if registered.path.rstrip("/") != parsed.path.rstrip("/"):
            continue
        if not query_keys <= set(candidate.safe_query_keys):
            continue
        return url
    return None


# --- registry ----------------------------------------------------------------
@lru_cache(maxsize=1)
def load_registry(path: str | None = None) -> dict[str, Action]:
    """id -> Action for every valid, enabled entry.

    Invalid entries are dropped, not raised on: the registry is loaded at
    request time, and one malformed row must not take chat down. The build-time
    gate (scripts/check_navigation.py) is where a bad row fails loudly.
    """
    target = Path(path) if path else REGISTRY_PATH
    if not target.exists():
        return {}
    import yaml  # noqa: PLC0415

    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001 — a broken file disables navigation, not chat
        return {}
    if not isinstance(data, list):
        return {}

    registry: dict[str, Action] = {}
    for record in data:
        if not isinstance(record, dict):
            continue
        try:
            action = Action(**{k: v for k, v in record.items()
                               if k in Action.__dataclass_fields__})
        except TypeError:
            continue
        if problems(action):
            continue
        registry[action.id] = action
    return registry


def problems(action: Action) -> list[str]:
    """Policy violations for one registry entry. Empty list = usable."""
    out: list[str] = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", action.id or ""):
        out.append("id must be lowercase kebab-case")
    problem = _structural_problem(action.destination)
    if problem:
        out.append(f"destination: {problem}")
    if not action.label_ar or not action.label_en:
        out.append("both label_ar and label_en are required")
    if not action.approved_by:
        out.append("an action must name who approved it")
    if not (0.0 <= action.min_confidence <= 1.0):
        out.append("min_confidence must be between 0 and 1")
    return out


def reload_registry() -> None:
    load_registry.cache_clear()
    declared_count.cache_clear()


@lru_cache(maxsize=1)
def declared_count(path: str | None = None) -> int:
    """How many actions the file declares, including unusable ones.

    `load_registry()` deliberately drops an entry that names no approver, so its
    length answers "how many destinations work", not "how many exist". /capabilities
    needs the difference to say *five destinations are awaiting approval* rather
    than silently showing an empty list, which reads as "this feature does not
    exist" instead of "nobody has approved it yet".
    """
    target = Path(path) if path else REGISTRY_PATH
    if not target.exists():
        return 0
    import yaml  # noqa: PLC0415

    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001 — same reasoning as load_registry
        return 0
    return sum(1 for record in data if isinstance(record, dict)) if isinstance(data, list) else 0


def get(action_id: str) -> Action | None:
    """Resolve an action id — the only thing a model is ever allowed to produce."""
    action = load_registry().get(action_id or "")
    return action if action and action.enabled else None


# --- resolution --------------------------------------------------------------
def _normalize(text: str) -> str:
    text = arabic.normalize_light(text or "").lower()
    return re.sub(r"[^\w\s؀-ۿ]+", " ", text).strip()


def _intent_match(question: str, action: Action) -> float:
    """Confidence that `question` asks for this action, from its phrase list.

    Phrase containment rather than similarity: the registry's intents are
    reviewed strings, and a deterministic match is auditable — a reviewer can
    say exactly which phrase fired. A learned matcher would put the destination
    back under the model's influence, which is the thing being avoided.
    """
    normalized = _normalize(question)
    if not normalized:
        return 0.0
    best = 0.0
    for phrase in list(action.intents_ar) + list(action.intents_en):
        candidate = _normalize(phrase)
        if not candidate:
            continue
        if normalized == candidate:
            return 1.0
        if candidate in normalized:
            # Longer phrases are more specific, so they earn more confidence.
            best = max(best, min(0.95, 0.7 + 0.05 * len(candidate.split())))
    return best


def resolve(
    question: str,
    passages: list[tuple[str, dict]] | None = None,
    locale: str = "en",
) -> dict | None:
    """Return the `navigation` event's action payload, or None.

    None is the common and correct outcome. An action is only offered when a
    reviewed intent phrase matched, or when the retrieved sources point at
    exactly one reviewed action — never as a guess.
    """
    registry = load_registry()
    if not registry:
        return None

    # 1. Explicit intent match, in either language.
    scored = [
        (action, _intent_match(question, action))
        for action in registry.values()
        if action.enabled
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    if scored and scored[0][1] >= scored[0][0].min_confidence:
        best, confidence = scored[0]
        # Ambiguity: two actions matched about equally well. Offering one would
        # be a coin flip on something that changes browser state.
        if len(scored) > 1 and abs(scored[1][1] - confidence) < 0.05:
            return None
        return {**best.payload(locale), "confidence": round(confidence, 2),
                "matched": "intent"}

    # 2. The retrieved sources reference exactly one reviewed action.
    if passages:
        source_ids = {meta.get("source") for _, meta in passages if meta.get("source")}
        referenced = [
            action for action in registry.values()
            if action.enabled and source_ids & set(action.source_ids)
        ]
        if len(referenced) == 1:
            action = referenced[0]
            return {**action.payload(locale), "confidence": 0.8, "matched": "source"}

    # 3. A model tool-call returning an action id is designed for but not
    #    enabled: it needs the release evaluation set's 20 navigation cases to
    #    demonstrate 100% destination precision first, and those cannot be
    #    written until an approved corpus exists.
    return None
