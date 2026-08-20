"""/capabilities — the portal's home view may only describe what exists.

The student portal shipped a dashboard of invented courses, a GPA, a credit
balance and a named student, over a backend whose scope guardrail declines every
personal-record question by design. The dashboard now renders this endpoint
instead, so these tests pin the properties that keep it honest:

  * an unapproved source is never named (the review queue is not a capability);
  * a navigation action with no approver is never named, but its existence is
    still counted, so "awaiting approval" and "does not exist" stay distinguishable;
  * the limits block agrees with `guardrails.check_scope`, which is what actually
    refuses the question — a UI claim that drifts from the guardrail is the bug
    this endpoint exists to prevent.
"""

import yaml

from ritaj import navigation, source_policy


def _client():
    from starlette.testclient import TestClient

    from ritaj.api import app

    return TestClient(app)


def _capabilities() -> dict:
    with _client() as c:
        r = c.get("/capabilities")
    assert r.status_code == 200
    return r.json()


# --- topics ------------------------------------------------------------------
def test_only_approved_sources_are_named():
    body = _capabilities()
    report = source_policy.load_and_validate(check_content=False)
    approved = {s.id for s in report.sources if s.approved}
    named = {t["id"] for t in body["topics"]}

    assert named == approved
    # Today that set is empty, and the endpoint must say so rather than
    # falling back to a hard-coded list of topics the corpus does not have.
    assert body["pending_topics"] == len(report.sources) - len(approved)


def test_review_queue_entries_are_counted_but_not_described():
    body = _capabilities()
    report = source_policy.load_and_validate(check_content=False)
    pending_titles = {s.title for s in report.sources if not s.approved}

    serialized = str(body)
    for title in pending_titles:
        assert title not in serialized, f"unapproved source {title!r} leaked into /capabilities"


# --- navigation --------------------------------------------------------------
def test_only_enabled_actions_are_named_and_the_rest_are_counted():
    body = _capabilities()
    enabled = {a.id for a in navigation.load_registry().values() if a.enabled}

    assert {a["id"] for a in body["navigation"]} == enabled
    declared = yaml.safe_load(navigation.REGISTRY_PATH.read_text(encoding="utf-8")) or []
    assert body["pending_navigation"] == len(declared) - len(enabled)
    # The kill switch is meaningful only if a disabled destination is invisible.
    assert "ritaj.birzeit.edu/reg/" not in str(body["navigation"])


def test_declared_count_sees_actions_load_registry_drops(tmp_path):
    """An unapproved action exists; it just is not usable."""
    registry = tmp_path / "navigation.yaml"
    registry.write_text(
        "- id: example-action\n"
        "  label_ar: مثال\n"
        "  label_en: Example\n"
        "  destination: https://ritaj.birzeit.edu/example\n"
        "  enabled: false\n"
        "  approved_by: \"\"\n",
        encoding="utf-8",
    )
    assert navigation.load_registry(str(registry)) == {}
    assert navigation.declared_count(str(registry)) == 1


# --- limits ------------------------------------------------------------------
def test_limits_match_the_guardrail_that_enforces_them():
    from ritaj import guardrails

    body = _capabilities()
    assert body["limits"]["personal_records"] is False
    assert body["limits"]["sign_in_on_your_behalf"] is False

    # If the guardrail ever stopped declining these, the portal's "what I can't
    # do" panel would be the lie instead.
    for question in ("what is my GPA?", "show me my grades", "ما هو رصيدي المالي؟"):
        verdict = guardrails.check_scope(question)
        assert verdict is not None, f"{question!r} is no longer declined"
        assert verdict["category"] == "personal_data"


def test_capabilities_answers_before_the_corpus_is_ready(reset_readiness):
    """It is a public probe, like /ready — never gated on initialization."""
    reset_readiness.reset_for_tests()
    body = _capabilities()
    assert body["ready"] is False
    assert body["corpus"]["chunks"] in (None, 0)
