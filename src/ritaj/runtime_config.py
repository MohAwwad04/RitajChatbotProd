"""Runtime-editable calibration parameters.

config.py holds *deployment* settings (URLs, model names) read once from .env.
This module holds the *tunable* pipeline parameters the /admin dashboard can edit
and save at runtime — retrieval breadth, chunking, the grounding threshold, the
generation knobs. Defaults live here; overrides are persisted to calibration.json
in the project root and loaded on startup, so a tuned value survives a restart.

The pipeline reads these live via get(), so most changes take effect on the next
request. The ones that change what's *stored* (chunk size / overlap / strategy)
need a re-index — `requires: "retrain"` in SPEC flags them for the UI.
"""

import json
import threading
from pathlib import Path

from .config import settings

_PATH = Path(settings.calibration_path)
_lock = threading.RLock()

# Default value for every tunable. The keys here are the whole editable surface;
# anything not in this dict is rejected by update() so the file can't grow junk.
DEFAULTS: dict = {
    # Retrieval funnel
    "top_k": 6,
    "candidates": 20,
    "rrf_k": 60,
    # Chunking (changing these needs a re-index to take effect)
    "chunk_target": 120,
    "chunk_overlap": 20,
    "chunk_strategy": "structure",  # "structure" | "window"
    # Grounding guardrail
    "support_threshold": 0.62,
    "min_claim_words": 4,
    # Generation
    "temperature": 0.2,
    "max_tokens": 1024,
    "llm_model": "",  # "" = fall back to config.settings.llm_model
}

# UI metadata: type, bounds, group, whether a re-index is needed, and a hint.
SPEC: list[dict] = [
    {"key": "top_k", "label": "Final top-k", "type": "int", "min": 1, "max": 20,
     "group": "Retrieval", "requires": "live",
     "help": "How many reranked chunks become the answer context."},
    {"key": "candidates", "label": "Candidate pool", "type": "int", "min": 5, "max": 100,
     "group": "Retrieval", "requires": "live",
     "help": "How many chunks each recall stage (dense, BM25) pulls before fusion."},
    {"key": "rrf_k", "label": "RRF k", "type": "int", "min": 1, "max": 200,
     "group": "Retrieval", "requires": "live",
     "help": "Rank-smoothing constant in Reciprocal Rank Fusion (60 is conventional)."},
    {"key": "chunk_target", "label": "Chunk size (words)", "type": "int", "min": 40, "max": 600,
     "group": "Chunking", "requires": "retrain",
     "help": "Target words per chunk. ~120 was the benchmarked sweet spot."},
    {"key": "chunk_overlap", "label": "Chunk overlap (words)", "type": "int", "min": 0, "max": 150,
     "group": "Chunking", "requires": "retrain",
     "help": "Word overlap between consecutive chunks (~15% of size)."},
    {"key": "chunk_strategy", "label": "Chunking strategy", "type": "enum",
     "options": ["structure", "window"], "group": "Chunking", "requires": "retrain",
     "help": "structure-aware (split on headings, keep tables/lists whole) vs a blind word window."},
    {"key": "support_threshold", "label": "Grounding threshold", "type": "float",
     "min": 0.0, "max": 1.0, "step": 0.01, "group": "Grounding", "requires": "live",
     "help": "Min cosine(sentence, best source) for a claim to count as supported."},
    {"key": "min_claim_words", "label": "Min claim words", "type": "int", "min": 1, "max": 20,
     "group": "Grounding", "requires": "live",
     "help": "Sentences shorter than this aren't treated as factual claims."},
    {"key": "temperature", "label": "LLM temperature", "type": "float",
     "min": 0.0, "max": 1.5, "step": 0.05, "group": "Generation", "requires": "live",
     "help": "Lower = more faithful/deterministic. 0.2 suits a grounded assistant."},
    {"key": "max_tokens", "label": "Max answer tokens", "type": "int", "min": 128, "max": 4096,
     "group": "Generation", "requires": "live",
     "help": "Upper bound on answer length."},
    {"key": "llm_model", "label": "LLM model tag", "type": "str",
     "group": "Generation", "requires": "live",
     "help": "OpenAI-compatible model id (blank = use the .env default)."},
]

_values: dict = dict(DEFAULTS)


def _coerce(key: str, value):
    """Coerce an incoming JSON value to the type declared for `key`."""
    spec = next((s for s in SPEC if s["key"] == key), None)
    t = spec["type"] if spec else "str"
    if t == "int":
        return int(value)
    if t == "float":
        return float(value)
    if t == "enum":
        return value if value in spec.get("options", []) else _values[key]
    return str(value)


def _load() -> None:
    if not _PATH.exists():
        return
    try:
        stored = json.loads(_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return
    with _lock:
        for k, v in stored.items():
            if k in DEFAULTS:
                try:
                    _values[k] = _coerce(k, v)
                except (ValueError, TypeError):
                    pass


def get(key: str):
    return _values[key]


def all_values() -> dict:
    return dict(_values)


def update(new: dict) -> dict:
    """Apply (and persist) a partial settings dict; unknown keys are ignored."""
    with _lock:
        for k, v in new.items():
            if k in DEFAULTS:
                try:
                    _values[k] = _coerce(k, v)
                except (ValueError, TypeError):
                    pass
        _save()
    return all_values()


def reset() -> dict:
    with _lock:
        _values.clear()
        _values.update(DEFAULTS)
        _save()
    return all_values()


def _save() -> None:
    try:
        _PATH.write_text(json.dumps(_values, indent=2), encoding="utf-8")
    except OSError:
        pass


_load()
