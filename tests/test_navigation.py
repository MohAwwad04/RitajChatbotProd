"""Phase 6 — the model may name an action; it may never name a destination.

The property under test is ADR-002's core claim: no input — a question, a
retrieved document, a compromised response — can cause the browser to open
something a human did not review.
"""

import textwrap

import pytest

from ritaj import guardrails, navigation


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """An approved, enabled registry — the shipped one is deliberately empty."""
    path = tmp_path / "navigation.yaml"
    path.write_text(textwrap.dedent("""
        - id: course-registration
          label_ar: فتح تسجيل المساقات
          label_en: Open course registration
          destination: https://ritaj.birzeit.edu/reg/
          auth_required: true
          requires_confirmation: true
          enabled: true
          owner: registration-office
          approved_by: registration-office / TICKET-142
          min_confidence: 0.75
          safe_query_keys: []
          source_ids: [registration-instructions-ar]
          intents_en:
            - open course registration
            - go to registration
          intents_ar:
            - افتح تسجيل المساقات
            - بدي انزل مساقات
        - id: course-browser
          label_ar: تصفح المساقات
          label_en: Browse courses
          destination: https://ritaj.birzeit.edu/hemis/courses
          auth_required: true
          requires_confirmation: true
          enabled: true
          owner: registration-office
          approved_by: registration-office / TICKET-142
          min_confidence: 0.75
          safe_query_keys: [term]
          source_ids: [course-browser]
          intents_en:
            - browse courses
          intents_ar:
            - تصفح المساقات
        - id: disabled-action
          label_ar: معطل
          label_en: Disabled
          destination: https://ritaj.birzeit.edu/disabled
          enabled: false
          approved_by: nobody
          intents_en:
            - open the disabled page
    """), encoding="utf-8")

    monkeypatch.setattr(navigation, "REGISTRY_PATH", path)
    navigation.reload_registry()
    yield path
    navigation.reload_registry()


# --- destination policy ------------------------------------------------------
@pytest.mark.parametrize("url,why", [
    ("https://www.birzeit.edu/en/admissions", "off-domain"),
    ("https://koha.birzeit.edu/", "off-domain sibling"),
    ("https://ritaj.birzeit.edu.attacker.test/reg/", "suffix trick"),
    ("https://evil-ritaj.birzeit.edu/reg/", "sibling subdomain"),
    ("https://attacker.test/ritaj.birzeit.edu/reg/", "host in path"),
    ("http://ritaj.birzeit.edu/reg/", "not https"),
    ("//ritaj.birzeit.edu/reg/", "scheme-relative"),
    ("javascript:alert(document.cookie)", "script scheme"),
    ("data:text/html,<script>alert(1)</script>", "data scheme"),
    ("https://user:pass@ritaj.birzeit.edu/reg/", "embedded credentials"),
    ("https://ritaj.birzeit.edu@attacker.test/", "userinfo confusion"),
    ("https://ritaj.birzeit.edu:8443/reg/", "non-standard port"),
    ("https://ritaj.birzeit.edu/reg/../../etc/passwd", "path traversal"),
    ("https://xn--ritj-hpa.birzeit.edu/reg/", "punycode homoglyph"),
    ("https://ritaj.birzeit.edu/reg/#javascript:alert(1)", "fragment"),
    ("https://ritaj.birzeit.edu\\@attacker.test/", "backslash"),
    ("https://ritaj.birzeit.edu/unregistered/path", "unregistered path"),
    ("", "empty"),
])
def test_hostile_destinations_are_rejected(registry, url, why):
    assert navigation.validate_destination(url) is None, why


def test_registered_destination_is_accepted(registry):
    assert navigation.validate_destination("https://ritaj.birzeit.edu/reg/") is not None


def test_only_declared_query_keys_survive(registry):
    assert navigation.validate_destination(
        "https://ritaj.birzeit.edu/hemis/courses?term=fall2026") is not None
    assert navigation.validate_destination(
        "https://ritaj.birzeit.edu/hemis/courses?redirect=https://attacker.test") is None


def test_a_disabled_action_opens_nothing(registry):
    assert navigation.get("disabled-action") is None
    assert navigation.validate_destination("https://ritaj.birzeit.edu/disabled") is None


def test_unknown_action_id_resolves_to_nothing(registry):
    """The model's only possible output is an id; a bad one must do nothing."""
    assert navigation.get("../../etc/passwd") is None
    assert navigation.get("course-registration-evil") is None
    assert navigation.get("") is None


# --- resolution --------------------------------------------------------------
def test_explicit_english_intent_resolves(registry):
    action = navigation.resolve("Open course registration please")
    assert action["id"] == "course-registration"
    assert action["url"] == "https://ritaj.birzeit.edu/reg/"
    assert action["requires_confirmation"] is True
    assert action["matched"] == "intent"


def test_explicit_arabic_intent_resolves_with_an_arabic_label(registry):
    action = navigation.resolve("بدي انزل مساقات", locale="ar")
    assert action["id"] == "course-registration"
    assert action["label"] == "فتح تسجيل المساقات"


def test_arabic_matching_survives_diacritics_and_spelling_variants(registry):
    """The registry phrase is normalized; a student's spelling need not match."""
    assert navigation.resolve("افتح تسجيل المساقات")["id"] == "course-registration"


def test_punctuation_between_words_does_not_break_a_match(registry):
    """Regression: internal punctuation used to leave a double space.

    `_normalize` replaces a run of punctuation with one space, so a comma
    *between* words produced "open  course registration" — and the reviewed
    phrase was then neither equal to nor contained in it, so the question
    resolved to nothing. Trailing punctuation always worked because `.strip()`
    removed the evidence, which is how this survived the 22-case eval set.
    """
    for question in [
        "open, course registration!",
        "open... course registration",
        "open — course registration",
        "افتح، تسجيل المساقات",
    ]:
        resolved = navigation.resolve(question)
        assert resolved is not None, question
        assert resolved["id"] == "course-registration", question

    # And the plain form is unchanged.
    assert navigation.resolve("open course registration")["id"] == "course-registration"


def test_an_ordinary_question_gets_no_action(registry):
    assert navigation.resolve("How much is one credit hour?") is None
    assert navigation.resolve("ما هو معدل النجاح؟") is None


def test_retrieved_source_can_point_at_one_action(registry):
    passages = [("Registration steps.", {"source": "registration-instructions-ar"})]
    action = navigation.resolve("how do I sign up for classes?", passages)
    assert action["id"] == "course-registration"
    assert action["matched"] == "source"


def test_sources_pointing_at_two_actions_offer_neither(registry):
    """Ambiguity must not be resolved by picking one."""
    passages = [
        ("Registration steps.", {"source": "registration-instructions-ar"}),
        ("Course list.", {"source": "course-browser"}),
    ]
    assert navigation.resolve("what should I do?", passages) is None


def test_resolution_never_returns_an_unvalidated_url(registry):
    """Whatever resolve() returns must survive the destination check."""
    for question in ["open course registration", "browse courses", "بدي انزل مساقات"]:
        action = navigation.resolve(question)
        if action:
            assert navigation.validate_destination(action["url"]) is not None


def test_empty_registry_means_no_navigation(tmp_path, monkeypatch):
    monkeypatch.setattr(navigation, "REGISTRY_PATH", tmp_path / "missing.yaml")
    navigation.reload_registry()
    assert navigation.resolve("open course registration") is None
    navigation.reload_registry()


def test_shipped_registry_is_valid_and_disabled():
    """The repository's registry: structurally sound, and nothing enabled yet."""
    import yaml

    records = yaml.safe_load(navigation.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert records, "registry should list candidate actions"
    for record in records:
        action = navigation.Action(**{
            k: v for k, v in record.items()
            if k in navigation.Action.__dataclass_fields__
        })
        assert navigation._structural_problem(action.destination) is None, action.id
        assert action.enabled is False, (
            f"{action.id} is enabled — confirm the destination and approver first"
        )


# --- registry hygiene --------------------------------------------------------
def test_an_entry_without_an_approver_is_dropped(tmp_path, monkeypatch):
    path = tmp_path / "nav.yaml"
    path.write_text(textwrap.dedent("""
        - id: unapproved
          label_ar: س
          label_en: X
          destination: https://ritaj.birzeit.edu/x
          enabled: true
          approved_by: ""
    """), encoding="utf-8")
    monkeypatch.setattr(navigation, "REGISTRY_PATH", path)
    navigation.reload_registry()
    assert navigation.load_registry() == {}
    navigation.reload_registry()


def test_an_off_domain_entry_is_dropped(tmp_path, monkeypatch):
    path = tmp_path / "nav.yaml"
    path.write_text(textwrap.dedent("""
        - id: smuggled
          label_ar: س
          label_en: X
          destination: https://attacker.test/reg/
          enabled: true
          approved_by: someone
    """), encoding="utf-8")
    monkeypatch.setattr(navigation, "REGISTRY_PATH", path)
    navigation.reload_registry()
    assert navigation.load_registry() == {}
    navigation.reload_registry()


def test_a_broken_registry_disables_navigation_without_breaking_chat(tmp_path, monkeypatch):
    path = tmp_path / "nav.yaml"
    path.write_text("this: is: not: a list", encoding="utf-8")
    monkeypatch.setattr(navigation, "REGISTRY_PATH", path)
    navigation.reload_registry()
    assert navigation.load_registry() == {}
    assert navigation.resolve("open course registration") is None
    navigation.reload_registry()


# --- execution policy --------------------------------------------------------
@pytest.mark.parametrize("question", [
    "Register COMP2310 for me",
    "Can you drop this course for me?",
    "Pay my fees",
    "pay my tuition",
    "سجل لي مساق COMP2310",
    "ادفع لي الرسوم",
])
def test_transactions_are_refused(question):
    result = guardrails.check_scope(question)
    assert result["allowed"] is False
    assert result["category"] == "transaction"


def test_a_refused_transaction_offers_the_page_instead(registry):
    """Refusing the action and offering the page are not in tension."""
    result = guardrails.check_scope("Register COMP2310 for me")
    assert result["category"] == "transaction"
    assert "open the right page" in result["response"]

    action = navigation.resolve("Register COMP2310 for me, open course registration")
    assert action["id"] == "course-registration"


@pytest.mark.parametrize("question", [
    "How do I register for courses?",
    "Where can I register?",
    "كيف أسجل المساقات؟",
])
def test_procedural_questions_are_not_treated_as_transactions(question):
    assert guardrails.check_scope(question)["allowed"] is True
