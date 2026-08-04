"""Phase 3 — retrieval filters, abstention, provenance in the prompt.

Model-free: the funnel's stages are stubbed so these run in CI. What is being
pinned is the *policy* applied around the models — which chunk wins when two are
equally relevant but one expired, and when the honest answer is "no source
covers that".
"""

from datetime import date

import pytest

from ritaj import answer_checks, generate, guardrails, retrieve, runtime_config


def _passage(source, text="Registration opens in week one.", **meta):
    base = {
        "source": source,
        "title": source.replace("-", " "),
        "url": f"https://ritaj.birzeit.edu/{source}",
        "language": "en",
        "as_of": "2026-08-01",
        "refresh": "weekly",
        "effective_from": "",
        "effective_to": "",
        "approved": True,
    }
    base.update(meta)
    return (text, base)


@pytest.fixture
def funnel(monkeypatch):
    """Stub dense/sparse/rerank so retrieval policy can be tested model-free."""
    state = {"corpus": {}, "scores": {}}

    def install(passages, scores):
        state["corpus"] = {f"c{i}": p for i, p in enumerate(passages)}
        state["scores"] = {p[0]: s for p, s in zip(passages, scores)}

    monkeypatch.setattr(retrieve, "_dense", lambda q, k: list(state["corpus"]))
    monkeypatch.setattr(retrieve.bm25, "search", lambda q, k: list(state["corpus"]))
    monkeypatch.setattr(retrieve.bm25, "corpus", lambda: state["corpus"])
    monkeypatch.setattr(
        retrieve,
        "rerank_scored",
        lambda q, passages, k: sorted(
            ((p, state["scores"][p[0]]) for p in passages),
            key=lambda pair: pair[1], reverse=True,
        )[:k],
    )
    return install


# --- language + date preferences --------------------------------------------
def test_arabic_question_prefers_arabic_sources(funnel):
    english = _passage("reg-en", "Registration opens in week one.", language="en")
    arabic = _passage("reg-ar", "يبدأ التسجيل في الأسبوع الأول.", language="ar")
    funnel([english, arabic], [1.0, 0.9])  # English scores higher before policy

    top = retrieve.retrieve("كيف أسجل المساقات؟", k=2)
    assert top[0][1]["source"] == "reg-ar", "Arabic question should surface Arabic source"


def test_mixed_script_question_is_treated_as_arabic():
    assert retrieve.query_language("كيف أسجل COMP2310؟") == "ar"
    assert retrieve.query_language("How do I register for COMP2310?") == "en"


def test_expired_source_loses_to_the_current_one(funnel):
    old = _passage("cal-2024", "Term starts 1 September 2024.",
                   effective_from="2024-09-01", effective_to="2025-01-15")
    now = _passage("cal-2026", "Term starts 5 September 2026.",
                   effective_from="2026-09-01", effective_to="2027-01-15")
    funnel([old, now], [2.0, 1.0])  # the expired one is textually a better match

    top = retrieve.retrieve("when does the term start?", k=2, on=date(2026, 8, 4))
    assert top[0][1]["source"] == "cal-2026"


def test_expired_source_wins_when_the_question_names_its_year(funnel):
    """A student asking about 2024 should get 2024, not this year's calendar."""
    old = _passage("cal-2024", "Term started 1 September 2024.",
                   effective_from="2024-09-01", effective_to="2025-01-15")
    now = _passage("cal-2026", "Term starts 5 September 2026.",
                   effective_from="2026-09-01", effective_to="2027-01-15")
    funnel([old, now], [2.0, 1.0])

    top = retrieve.retrieve("when did the term start in 2024?", k=2, on=date(2026, 8, 4))
    assert top[0][1]["source"] == "cal-2024"


def test_year_extraction_handles_academic_year_forms():
    assert retrieve.years_mentioned("the 2025/2026 calendar") == {"2025", "2026"}
    assert retrieve.years_mentioned("fall 2024") == {"2024"}
    assert retrieve.years_mentioned("no year here") == set()


# --- deduplication + abstention ---------------------------------------------
def test_adjacent_chunks_of_one_section_do_not_fill_the_context(funnel):
    header = "Registration > How to register"
    chunks = [
        _passage("reg", f"{header}\n\nStep {i} of the process.") for i in range(1, 5)
    ]
    other = _passage("fees", "Fees > Payment\n\nPay at the Finance office.")
    funnel(chunks + [other], [3.0, 2.9, 2.8, 2.7, 1.0])

    top = retrieve.retrieve("how do I register?", k=4)
    sources = [meta["source"] for _, meta in top]
    assert sources.count("reg") == 1, "one chunk per section should survive"
    assert "fees" in sources, "the other document should get a slot"


def test_nothing_above_the_floor_means_no_passages(funnel, monkeypatch):
    funnel([_passage("reg")], [-9.0])
    monkeypatch.setattr(runtime_config, "get",
                        lambda k: -2.0 if k == "min_relevance" else runtime_config.DEFAULTS[k])
    assert retrieve.retrieve("what is the price of tea in China?") == []


def test_floor_keeps_a_genuine_match(funnel):
    funnel([_passage("reg")], [1.5])
    assert len(retrieve.retrieve("how do I register?")) == 1


# --- provenance reaches the model -------------------------------------------
def test_system_prompt_claims_independence_not_officialness():
    prompt = generate.SYSTEM_PROMPT.lower()
    assert "independent" in prompt
    assert "not an official" in prompt
    assert "official birzeit university student helper" not in prompt


def test_source_header_carries_url_and_capture_date():
    header = generate._source_header(1, _passage("reg")[1])
    assert "https://ritaj.birzeit.edu/reg" in header
    assert "captured: 2026-08-01" in header


def test_source_header_marks_a_stale_snapshot():
    meta = _passage("reg", as_of="2020-01-01", refresh="weekly")[1]
    assert "OUT OF DATE" in generate._source_header(1, meta)


def test_prompt_fences_every_source():
    passages = [_passage("reg"), _passage("fees")]
    prompt = generate.build_user_prompt("how do I register?", passages)
    assert prompt.count("BEGIN SOURCE") == 2
    assert prompt.count("END SOURCE") == 2
    assert "untrusted content" in prompt


# --- grounding describes the text the student sees --------------------------
def test_finalize_rechecks_the_repaired_text(monkeypatch):
    """The verdict must describe what is displayed, not the discarded draft."""
    calls = []

    def fake_check(text, passages, threshold=None):
        calls.append(text)
        if len(calls) == 1:
            return {
                "verdict": "partial",
                "sentences": [
                    {"text": "Registration opens in week one [1].", "grounded": True},
                    {"text": "Tuition is JD 999 [1].", "grounded": False},
                ],
            }
        return {"verdict": "grounded", "n_claims": 1, "uncited_claims": 0}

    monkeypatch.setattr("ritaj.grounding.check", fake_check)
    final, report, repaired = generate.finalize("draft", [_passage("reg")], "how much?")

    assert repaired is True
    assert "JD 999" not in final
    assert report["verdict"] == "grounded", "report must describe the repaired text"
    assert report["final"] == "repaired"
    assert len(calls) == 2


def test_finalize_falls_back_when_repair_still_fails(monkeypatch):
    def fake_check(text, passages, threshold=None):
        if text == "draft":
            return {"verdict": "partial",
                    "sentences": [{"text": "Tuition is JD 999.", "grounded": True}]}
        return {"verdict": "ungrounded"}

    monkeypatch.setattr("ritaj.grounding.check", fake_check)
    final, report, repaired = generate.finalize("draft", [_passage("reg")], "how much?")
    assert final == generate.GROUNDING_FALLBACK
    assert report["final"] == "fallback"


def test_fallbacks_match_the_question_language():
    assert generate.localized("en", "ar", "كيف أسجل؟") == "ar"
    assert generate.localized("en", "ar", "how do I register?") == "en"


# --- answer-level checks -----------------------------------------------------
def test_citation_coverage_is_reported():
    report = {"n_claims": 4, "uncited_claims": 1}
    checks = answer_checks.run("Fees are due [1]. Term starts later.",
                               [_passage("fees")], report)
    assert checks["citation_coverage"] == 0.75
    assert checks["cited_sources"] == 1


def test_stale_cited_source_is_flagged():
    stale = _passage("cal", as_of="2020-01-01", refresh="weekly")
    checks = answer_checks.run("Term starts 5 September [1].", [stale],
                               {"n_claims": 1, "uncited_claims": 0})
    assert checks["uses_stale_source"] is True
    assert "cal" in checks["stale_sources"]


def test_contradictory_effective_windows_are_flagged_when_dates_are_stated():
    a = _passage("cal-2024", effective_from="2024-09-01", effective_to="2025-01-15")
    b = _passage("cal-2026", effective_from="2026-09-01", effective_to="2027-01-15")
    stated = answer_checks.run("Term starts 1 September 2024 [1] and ends in 2027 [2].",
                               [a, b], {"n_claims": 2, "uncited_claims": 0})
    assert stated["contradictory_dates"] is True

    # Same two sources backing a procedural answer with no dates: not a problem.
    procedural = answer_checks.run("Open the Registration module [1] and confirm [2].",
                                   [a, b], {"n_claims": 2, "uncited_claims": 0})
    assert procedural["contradictory_dates"] is False


# --- bilingual refusals ------------------------------------------------------
@pytest.mark.parametrize("question", [
    "What's my current balance?",
    "What is my final GPA?",
    "Show me my fall semester schedule",
    "Can you log in to Ritaj for me?",
])
def test_modified_personal_requests_are_still_declined(question):
    """'my *current* balance' used to slip past the bare-noun pattern."""
    assert guardrails.check_scope(question)["category"] == "personal_data"


@pytest.mark.parametrize("question", [
    "How do I check my balance?",
    "Where do I find my grades on Ritaj?",
    "How is my GPA calculated?",
])
def test_navigational_questions_are_still_answered(question):
    """The false-refusal contract: these want a path, not a value."""
    assert guardrails.check_scope(question)["allowed"] is True


def test_arabic_question_gets_an_arabic_refusal():
    result = guardrails.check_scope("ما هو معدلي التراكمي؟")
    assert result["category"] == "personal_data"
    assert any("؀" <= ch <= "ۿ" for ch in result["response"])


def test_english_question_gets_an_english_refusal():
    result = guardrails.check_scope("What is my GPA?")
    assert not any("؀" <= ch <= "ۿ" for ch in result["response"])
