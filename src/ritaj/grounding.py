"""Grounding guardrail — does the answer actually rest on the sources?

The system prompt (generate.py) *asks* Gemma to answer only from the numbered
sources and cite them, but nothing verifies it did. This module checks, after
generation, that each factual sentence is:

  1. semantically supported by at least one retrieved chunk (cosine similarity,
     reusing the e5 embedder we already load — no second model), and
  2. free of invented numbers (every number in a claim appears in some source),
     and backed by valid citation markers [n].

It returns a verdict plus per-sentence detail. The **concrete, dangerous**
signals — a number that appears in no source, or a citation that points past the
end of the source list — force an "ungrounded" verdict, which generate.repair()
then withholds. A merely low semantic-similarity sentence (no bad number, valid
citations) yields "partial": kept but badged, to avoid refusing a correct answer
that's just phrased far from the source.
"""

import re

import numpy as np

from . import arabic, runtime_config
from .embeddings import embed_passages

# Defaults; the live values are tunable from /admin (runtime_config):
#   support_threshold — min cosine(sentence, best source) for a supported claim
#   min_claim_words   — shorter fragments ("1.", "Note:") aren't treated as claims
SUPPORT_THRESHOLD = 0.62
MIN_CLAIM_WORDS = 4

_CITE = re.compile(r"\[(\d+)\]")
_SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n+")
# Numbers carry the facts this bot must never invent (fees, dates, GPA, phones).
# Semantic similarity can't tell "JD 125" from "JD 500" — near-identical in
# embedding space — so every number in a claim must appear in some source.
# Capture grouped numbers (so "1,250" / "3.7" stay whole); separators normalized.
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Phone/contact numbers are written with separators (+970-2-2982057), and an LLM
# may reformat the SAME number — drop the hyphens, add a 00 prefix, regroup the
# digits — which the per-group check would then flag as invented. So we also read
# a "joined" form: a one-line run of digits glued across phone separators
# (+ - ( ) space/tab), leading zeros trimmed. A number counts as supported if it
# also appears within a source's joined phone number. (Newlines are NOT joiners,
# so stacked table/list numbers don't fuse into one bogus phone.)
_PHONE_RUN = re.compile(r"\d[\d \t()+\-]*\d")
# Hallmarks of an honest refusal / handoff. Only treated as a refusal when the
# sentence has NO citation and NO number — otherwise a real answer like "contact
# Registration at +970-2-2982057 [1]" would wrongly bypass the guardrail.
_REFUSAL = re.compile(
    r"\b(can't|cannot|could not|couldn't|don't have|do not have|not in the|"
    r"isn't in|i'm sorry|unable|don't know|do not know|contact)\b",
    re.I,
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _canon(num: str) -> str:
    """Canonical digit form: commas dropped; leading zeros trimmed on integers
    (so "00970" == "970"), decimals left intact (so "0.5" / "3.7" keep their form)."""
    num = num.replace(",", "")
    if "." in num:
        return num
    return num.lstrip("0") or "0"


def _numset(text: str) -> set[str]:
    """Canonical numbers in `text` (Arabic-Indic digits folded, commas stripped,
    integer leading-zeros trimmed)."""
    return {_canon(m) for m in _NUM.findall(arabic.normalize_light(text))}


def _phoneset(text: str) -> set[str]:
    """Joined phone-number digit strings (>=7 digits) in `text`, leading zeros
    trimmed — so the same contact number survives any separator/prefix reformat."""
    out: set[str] = set()
    for run in _PHONE_RUN.findall(arabic.normalize_light(text)):
        digits = re.sub(r"\D", "", run)
        if len(digits) >= 7:
            out.add(digits.lstrip("0") or "0")
    return out


def check(
    answer: str,
    passages: list[tuple[str, dict]],
    threshold: float | None = None,
) -> dict:
    """Score how well `answer` is grounded in `passages` (the retrieved chunks).

    `threshold` is the minimum cosine(sentence, best source) for a claim to count
    as semantically supported. When None it uses the live runtime value (tunable
    from /admin); evaluation.tune_threshold sweeps it to pick the best.
    """
    if threshold is None:
        threshold = runtime_config.get("support_threshold")
    min_claim_words = runtime_config.get("min_claim_words")
    sents = _sentences(answer)
    n = len(passages)
    if not sents:
        return {"verdict": "empty", "support_rate": 0.0, "n_claims": 0, "sentences": []}

    # Embed sentences + chunks together; cosine == dot since e5 vectors are unit.
    chunk_texts = [doc for doc, _ in passages]
    embs = np.asarray(embed_passages(sents + chunk_texts), dtype=float)
    sent_e, chunk_e = embs[: len(sents)], embs[len(sents):]
    sims = sent_e @ chunk_e.T if n else np.zeros((len(sents), 0))
    all_nums = set().union(*[_numset(t) for t in chunk_texts]) if chunk_texts else set()
    all_phones = set().union(*[_phoneset(t) for t in chunk_texts]) if chunk_texts else set()

    def _supported(num: str) -> bool:
        # Supported if the source has it as a standalone number, or as part of a
        # cited phone number (covers separator/prefix/regrouping reformats).
        return num in all_nums or num in all_phones or any(num in p for p in all_phones)

    details = []
    for i, sent in enumerate(sents):
        cites = [int(c) for c in _CITE.findall(sent)]
        valid = sorted({c for c in cites if 1 <= c <= n})
        invalid = sorted({c for c in cites if c < 1 or c > n})
        if n:
            best = int(np.argmax(sims[i]))
            support = float(sims[i][best])
        else:
            best, support = -1, 0.0

        # A number not present in ANY source is invented (citation markers
        # stripped first so "[1]" isn't read as the number 1). Checking against
        # all sources — not only the cited one — avoids false alarms when the
        # model cites the wrong source for a fact that is genuinely in the corpus.
        bare = _CITE.sub("", sent)
        sent_nums = _numset(bare) | _phoneset(bare)
        bad_nums = sorted(n for n in sent_nums if not _supported(n))

        # Refusal only when there's nothing to verify (no citation, no number).
        looks_refusal = bool(_REFUSAL.search(sent)) and not valid and not invalid and not sent_nums
        is_claim = len(sent.split()) >= min_claim_words and not looks_refusal
        grounded = not is_claim or (support >= threshold and not bad_nums and not invalid)
        details.append({
            "text": sent,
            "support": round(support, 3),
            "best_source": best + 1 if best >= 0 else None,
            "cites": valid,
            "invalid_cites": invalid,
            "unsupported_numbers": bad_nums,
            "is_claim": is_claim,
            "grounded": grounded,
        })

    claims = [d for d in details if d["is_claim"]]
    grounded_claims = [d for d in claims if d["grounded"]]
    # Concrete hallucination signals: an invented number or a fabricated citation.
    hard_fail = any(d["unsupported_numbers"] or d["invalid_cites"] for d in claims)
    support_rate = len(grounded_claims) / len(claims) if claims else 1.0

    if not claims:
        verdict = "ok"  # a refusal / no factual claims to ground
    elif support_rate == 1.0 and not hard_fail:
        verdict = "grounded"
    elif hard_fail or support_rate < 0.5:
        verdict = "ungrounded"  # → repaired (withheld) by generate.repair()
    else:
        verdict = "partial"  # soft: low similarity only, no bad number/citation

    return {
        "verdict": verdict,
        "support_rate": round(support_rate, 3),
        "threshold": threshold,
        "n_claims": len(claims),
        "n_grounded": len(grounded_claims),
        "invalid_citations": any(d["invalid_cites"] for d in details),
        "uncited_claims": sum(1 for d in claims if not d["cites"]),
        "sentences": details,
    }
