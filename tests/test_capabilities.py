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
    """An unapproved SOURCE is never described. A navigation label may share words.

    Scoped to the blocks that describe the corpus, not to `str(body)`. Searching
    the whole payload conflated two different things: the source titled
    «التقويم الأكاديمي» is unapproved and must not be described, while the
    navigation button «فتح التقويم الأكاديمي» is approved, enabled, and exists
    precisely to be named. The button's label contains the document's title as a
    substring, so a whole-body search reported a leak that was not one — and
    would keep doing so for any reviewed button sharing a noun with a document.
    """
    body = _capabilities()
    report = source_policy.load_and_validate(check_content=False)
    pending = [s for s in report.sources if not s.approved]

    described = str({"topics": body["topics"], "corpus": body["corpus"]})
    for source in pending:
        assert source.title not in described, (
            f"unapproved source {source.title!r} leaked into /capabilities"
        )
        assert source.id not in described, (
            f"unapproved source id {source.id!r} leaked into /capabilities"
        )
    assert pending, "no unapproved sources left — this test proves nothing now"


# --- navigation --------------------------------------------------------------
def test_only_enabled_actions_are_named_and_the_rest_are_counted():
    body = _capabilities()
    enabled = {a.id for a in navigation.load_registry().values() if a.enabled}

    assert {a["id"] for a in body["navigation"]} == enabled
    declared_records = yaml.safe_load(
        navigation.REGISTRY_PATH.read_text(encoding="utf-8")) or []
    assert body["pending_navigation"] == len(declared_records) - len(enabled)

    # The kill switch is meaningful only if a disabled destination is invisible.
    # Derived from the file rather than naming one URL: the previous version
    # hard-coded /reg/, which silently stopped testing anything the day /reg/
    # was approved — the assertion still passed, against the wrong action.
    serialized = str(body["navigation"])
    disabled = [r for r in declared_records if not r.get("enabled")]
    for record in disabled:
        assert record["destination"] not in serialized, (
            f"disabled destination {record['id']} leaked into /capabilities"
        )
    assert disabled, (
        "every action is enabled, so this test no longer proves the kill switch "
        "hides anything — disable one, or delete this assertion deliberately"
    )


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
    """It is a public probe, like /ready — never gated on initialization.

    The chunk assertion used to read `in (None, 0)`, which encoded "no corpus
    has been published" — a fact about the working tree on the day it was
    written, not a property of the endpoint. It broke the moment a corpus was
    published, which is correct progress, and a test that fails on correct
    progress only teaches people to edit the assertion. What matters here is
    that the endpoint ANSWERS while readiness is still false, and that whatever
    it reports about the corpus is coherent.
    """
    reset_readiness.reset_for_tests()
    body = _capabilities()
    assert body["ready"] is False           # initialization has not run
    corpus = body["corpus"]
    assert "chunks" in corpus and "version" in corpus
    # Coherent either way: no corpus, or a real one with a version and a count.
    if corpus["chunks"]:
        assert corpus["version"], "chunks reported without a corpus version"
        assert corpus["chunks"] > 0
    # Provenance always travels, so a client can never fail to ask.
    assert isinstance(corpus.get("verified"), bool)


# --- admin display surfaces on a fresh deployment ---------------------------
def test_admin_points_reports_no_corpus_instead_of_500(monkeypatch):
    """A fresh deployment has no collection — and that is when an operator looks.

    /admin/points returned 500 on the live Space because vectorstore.get_all()
    raises when the collection was never created. A stack trace there reads as
    "the console is broken" when the true answer is "nothing is indexed yet".
    """
    from starlette.testclient import TestClient

    from ritaj import vectorstore
    from ritaj.api import app

    monkeypatch.setattr(vectorstore, "collection_ready", lambda: False)
    with TestClient(app) as c:
        r = c.get("/admin/points")
    assert r.status_code == 200
    body = r.json()
    assert body["points"] == []
    assert body["corpus"] == "none-indexed"


def test_collection_ready_is_not_a_retrieval_fallback():
    """An absent collection must stay distinguishable from an empty one.

    collection_ready() is for display surfaces only. Folding it into get_all()
    or count() as a "return empty" fallback would make pointing at the wrong
    Qdrant cluster look identical to a corpus that has not been built — the
    exact failure the explicit QDRANT_MODE work exists to prevent.
    """
    import inspect

    from ritaj import vectorstore

    for name in ("get_all", "count", "query"):
        source = inspect.getsource(getattr(vectorstore, name))
        assert "collection_ready" not in source, (
            f"vectorstore.{name} must not swallow a missing collection"
        )
