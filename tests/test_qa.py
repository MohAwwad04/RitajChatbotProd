"""QA tests — answer-quality contracts, scored model-free in CI.

The full-pipeline QA eval (ritaj.evaluation.run_golden, driven by
scripts/eval_golden.py) needs the embedder + a live LLM. These tests pin the
parts of answer quality that are deterministic, so they run in CI with no model:

  • Dataset health — the golden + retrieval sets the live eval scores against are
    well-formed (every answerable case names a real source file and the gold
    fact(s) it must contain; every refuse case carries no answer key).
  • False-refusal contract — the project holds false-refusal at 0%: general
    policy questions (no possessive) must NOT be declined by the scope guardrail.
  • Grounding verdicts — a correctly-cited, supported answer is `grounded`; an
    answer with no factual claim is `ok`; the dangerous cases are `ungrounded`.
  • Repair contract — how verdicts turn into the final answer the student sees.
  • Scorer — the substring grader folds Arabic so an Arabic answer matches a
    digit-based gold fact.
"""

from pathlib import Path

import pytest

from ritaj import grounding
from ritaj.evaluation import (
    GOLDEN,
    RETRIEVAL_EVAL,
    _contains_all,
    _declined,
    _norm,
)
from ritaj.generate import GROUNDING_FALLBACK, repair
from ritaj.guardrails import check_scope

# The golden set targets the development corpus. Its documents moved to
# data/quarantine/ when the Ritaj-only source policy excluded all of them —
# see that folder's README and ritaj.evaluation._DATA_DIR.
_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "quarantine"


# --- Golden / retrieval datasets are well-formed ----------------------------
def test_golden_answerable_cases_are_well_formed():
    answerable = [c for c in GOLDEN if c["type"] == "answerable"]
    assert len(answerable) >= 15
    for c in answerable:
        assert c["q"].strip()
        assert c["expect_source"].endswith(".md")
        assert isinstance(c["answer_contains"], list) and c["answer_contains"]
        assert all(tok.strip() for tok in c["answer_contains"])


def test_golden_refuse_cases_carry_no_answer_key():
    # A refuse case must not assert a fact to contain — there's nothing to answer.
    for c in GOLDEN:
        if c["type"] == "refuse":
            assert "answer_contains" not in c and "expect_source" not in c


def test_golden_types_are_known_and_questions_unique():
    assert all(c["type"] in {"answerable", "refuse"} for c in GOLDEN)
    questions = [c["q"] for c in GOLDEN]
    assert len(questions) == len(set(questions))


def test_every_golden_expect_source_exists_on_disk():
    # The eval can only credit retrieval if the source file is really in the corpus.
    for c in GOLDEN:
        if c["type"] == "answerable":
            assert (_DATA_DIR / c["expect_source"]).is_file(), c["expect_source"]


def test_retrieval_eval_pairs_are_well_formed():
    assert len(RETRIEVAL_EVAL) >= 15
    for query, gold in RETRIEVAL_EVAL:
        assert query.strip() and gold.strip()


# --- False-refusal contract: general policy questions are NOT declined ------
@pytest.mark.parametrize("q", [
    "What GPA do I need to graduate?",
    "How are grades calculated?",
    "How do I drop a course?",
    "How much does one credit hour cost?",
    "When does the fall semester begin?",
    "What documents do I need to apply for admission?",
    "كيف احسب المعدل؟",
    "متى تبدأ الدراسة في الفصل الأول؟",
])
def test_general_policy_questions_are_allowed(q):
    assert check_scope(q)["allowed"]


# Navigational questions carry a possessive ("my grades") but ask HOW/WHERE to do
# something — the corpus documents the Ritaj path, so they must NOT be declined
# for lack of auth (the over-refusal this guard previously caused).
@pytest.mark.parametrize("q", [
    "How do I view my grades on Ritaj?",
    "How do I check my grades?",
    "How do I see my timetable?",
    "How do I request my transcript?",
    "Where do I find my schedule?",
    "How can I view my registration status?",
    "كيف اشوف علاماتي؟",
    "كيف احسب معدلي؟",
])
def test_navigational_personal_questions_are_allowed(q):
    assert check_scope(q)["allowed"]


# Value-lookups want the data itself (needs auth) — these must still be declined.
@pytest.mark.parametrize("q", [
    "What is my GPA?",
    "show me my grades",
    "How much do I owe?",
    "what is my balance",
    "Am I registered for any courses?",
    "ما هو معدلي؟",
    "اريد علاماتي",
])
def test_personal_value_lookups_are_still_blocked(q):
    out = check_scope(q)
    assert not out["allowed"] and out["category"] == "personal_data"


# --- Grounding verdicts (semantic check stubbed to isolate the rest) --------
@pytest.fixture
def unit_embedder(monkeypatch):
    # Identical unit vectors -> cosine 1.0, so only the number/citation/refusal
    # logic decides the verdict.
    monkeypatch.setattr(
        grounding, "embed_passages",
        lambda texts: [[1.0] + [0.0] * 1023 for _ in texts],
    )


def test_supported_cited_claim_is_grounded(unit_embedder):
    src = [("Most programs cost JD 125 per credit hour.", {"source": "fees.md"})]
    out = grounding.check("Most programs cost JD 125 per credit hour [1].", src)
    assert out["verdict"] == "grounded" and out["n_claims"] == 1


def test_contact_answer_with_a_real_phone_is_grounded(unit_embedder):
    # A legitimate handoff that quotes a number from the source must still pass
    # the guardrail (not be waved through as a refusal).
    src = [("Call the Computer Center at 2982057 to reset your password.", {})]
    out = grounding.check("Contact the Computer Center at 2982057 [1].", src)
    assert out["verdict"] == "grounded"


def test_answer_with_no_factual_claim_is_ok(unit_embedder):
    src = [("Most programs cost JD 125 per credit hour.", {})]
    refusal = "I don't have that in the sources. Please contact Registration."
    assert grounding.check(refusal, src)["verdict"] == "ok"


# --- Repair contract: verdict -> what the student sees ----------------------
def test_repair_withholds_ungrounded_answer():
    out, repaired = repair("Tuition is JD 500 [1].", {"verdict": "ungrounded"})
    assert repaired and out == GROUNDING_FALLBACK


def test_repair_keeps_grounded_answer_verbatim():
    out, repaired = repair("Tuition is JD 125 [1].", {"verdict": "grounded"})
    assert not repaired and out == "Tuition is JD 125 [1]."


def test_repair_trims_only_the_flagged_sentence_in_a_partial():
    report = {"verdict": "partial", "sentences": [
        {"text": "Tuition is JD 125 per credit hour [1].", "grounded": True},
        {"text": "It also includes free parking [1].", "grounded": False},
    ]}
    out, repaired = repair(
        "Tuition is JD 125 per credit hour [1]. It also includes free parking [1].",
        report)
    assert repaired and "JD 125" in out and "parking" not in out


# --- Scorer: the substring grader and decline detector ----------------------
def test_scorer_folds_arabic_digits_so_arabic_answers_match():
    # ٢٠٢٥ must match the gold token "2025" in an Arabic answer.
    assert _contains_all("تبدأ الدراسة في ٢٠٢٥", ["2025"])
    assert not _contains_all("tuition is JD 125", ["jd 160"])


def test_declined_detects_fallback_and_refusals_but_not_real_answers():
    assert _declined(GROUNDING_FALLBACK)
    assert _declined("I'm sorry, I don't have that information.")
    assert not _declined("Most programs cost JD 125 per credit hour [1].")
