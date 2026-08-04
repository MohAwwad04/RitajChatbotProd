"""Phase 1 — the service can say what state it is in, and fails safely.

The production outage this covers: the app did all its initialization before
binding the port, so the platform's health check saw nothing at all and killed
a container that would have become healthy. These tests pin the three
behaviours that make that impossible to repeat.
"""

import httpx
import pytest

from ritaj import errors, llm, readiness


def _client():
    from starlette.testclient import TestClient

    from ritaj.api import app

    return TestClient(app)


# --- liveness vs readiness ---------------------------------------------------
def test_live_answers_while_still_initializing(reset_readiness):
    """/live must never wait on models, the store, or the network."""
    reset_readiness.reset_for_tests()
    with _client() as c:
        r = c.get("/live")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


def test_ready_is_503_until_initialization_completes(reset_readiness):
    with _client() as c:
        r = c.get("/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "not-ready"

        reset_readiness.start_background_init(lambda: {"chunks": 7})
        assert reset_readiness.wait_ready(timeout=5)

        r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["state"] == "ready"
    assert r.json()["detail"]["chunks"] == 7


def test_ready_reports_failure_without_leaking_internals(reset_readiness):
    def boom():
        raise RuntimeError("qdrant path /home/user/secret is not writable")

    reset_readiness.start_background_init(boom)
    assert reset_readiness.wait_ready(timeout=5) is False
    assert reset_readiness.state() == "failed"

    with _client() as c:
        r = c.get("/ready")
    assert r.status_code == 503
    # The operator needs the reason; it is on the protected /ready surface, not
    # in a student-facing chat response.
    assert "RuntimeError" in r.json()["error"]


def test_health_alias_still_reports_readiness(reset_readiness):
    with _client() as c:
        assert c.get("/health").status_code == 503
        reset_readiness.start_background_init(lambda: {})
        assert reset_readiness.wait_ready(timeout=5)
        assert c.get("/health").status_code == 200


# --- chat refuses with a code, not a dead socket -----------------------------
def test_chat_returns_initializing_code_when_not_ready(monkeypatch, reset_readiness):
    from ritaj.config import settings

    # Enter the client first: the lifespan reads startup_init, and flipping it
    # before would make the app launch the real (model-loading) bootstrap.
    with _client() as c:
        monkeypatch.setattr(settings, "startup_init", True)
        r = c.post("/chat", json={"message": "when does the semester start?"})
    assert r.status_code == 503
    assert r.json()["code"] == "INITIALIZING"
    assert r.headers["Retry-After"] == "10"


def test_chat_reports_not_ready_after_failed_init(monkeypatch, reset_readiness):
    from ritaj.config import settings

    with _client() as c:
        reset_readiness.start_background_init(
            lambda: (_ for _ in ()).throw(RuntimeError("x"))
        )
        assert reset_readiness.wait_ready(timeout=5) is False
        monkeypatch.setattr(settings, "startup_init", True)
        r = c.post("/chat", json={"message": "hi"})
    assert r.status_code == 503
    assert r.json()["code"] == "NOT_READY"


def test_startup_timings_are_recorded(reset_readiness):
    reset_readiness.mark("listening")
    reset_readiness.mark("listening")  # first write wins
    snap = reset_readiness.snapshot()
    assert "listening" in snap["timings_ms"]
    assert snap["uptime_ms"] >= 0


# --- LLM client resilience ---------------------------------------------------
@pytest.fixture(autouse=True)
def _fresh_breaker():
    """Each test gets its own circuit breaker; failures must not leak across."""
    llm._breaker = llm._CircuitBreaker()
    yield
    llm._breaker = llm._CircuitBreaker()


def _ok_response(text="hello"):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
        request=httpx.Request("POST", "http://test/chat/completions"),
    )


def test_chat_retries_once_on_transient_failure(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("connection reset")
        return _ok_response("recovered")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setattr(llm, "_sleep_before_retry", lambda _a: None)

    assert llm.chat([{"role": "user", "content": "hi"}]) == "recovered"
    assert len(calls) == 2


def test_chat_does_not_retry_a_client_error(monkeypatch):
    """A 400 is our fault, not weather. Retrying just spends quota twice."""
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return httpx.Response(400, text="bad model id",
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(errors.PublicError) as exc:
        llm.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1
    assert exc.value.code == "LLM_UNAVAILABLE"


def test_public_error_hides_provider_detail_from_students():
    err = errors.LLM_UNAVAILABLE(detail="HTTP 401 at accounts/abc123secret/ai/v1")
    body = err.public()
    assert body["code"] == "LLM_UNAVAILABLE"
    assert "abc123secret" not in body["message"]
    assert "abc123secret" in str(err)  # still available to the log


def test_circuit_opens_after_repeated_failures_and_fails_fast(monkeypatch):
    def always_fail(url, **kw):
        raise httpx.ConnectError("provider down")

    monkeypatch.setattr(llm.httpx, "post", always_fail)
    monkeypatch.setattr(llm, "_sleep_before_retry", lambda _a: None)

    for _ in range(3):  # 2 attempts each -> 6 consecutive failures
        with pytest.raises(errors.PublicError):
            llm.chat([{"role": "user", "content": "hi"}])

    assert llm.circuit_state()["open"] is True

    # With the circuit open we must fail without touching the provider at all.
    def must_not_be_called(url, **kw):  # pragma: no cover - asserts absence
        raise AssertionError("called the provider while the circuit was open")

    monkeypatch.setattr(llm.httpx, "post", must_not_be_called)
    with pytest.raises(errors.PublicError) as exc:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc.value.code == "LLM_UNAVAILABLE"
    assert exc.value.retry_after is not None


def test_stream_is_not_retried_after_a_token_was_emitted(monkeypatch):
    """Retrying mid-stream would replay text the student already saw."""
    attempts = []

    class FakeStream:
        def __init__(self, attempt):
            self.attempt = attempt

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Reg"}}]}'
            raise httpx.ReadTimeout("provider stalled mid-stream")

    def fake_stream(method, url, **kw):
        attempts.append(url)
        return FakeStream(len(attempts))

    monkeypatch.setattr(llm.httpx, "stream", fake_stream)
    monkeypatch.setattr(llm, "_sleep_before_retry", lambda _a: None)

    out = []
    with pytest.raises(errors.PublicError):
        for delta in llm.chat_stream([{"role": "user", "content": "hi"}]):
            out.append(delta)

    assert out == ["Reg"]
    assert len(attempts) == 1, "a partially delivered stream must not be retried"


def test_stream_retries_when_nothing_was_emitted_yet(monkeypatch):
    attempts = []

    class FailingStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            raise httpx.ConnectError("cold start")

        def iter_lines(self):  # pragma: no cover - never reached
            return iter(())

    class GoodStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield "data: [DONE]"

    def fake_stream(method, url, **kw):
        attempts.append(url)
        return FailingStream() if len(attempts) == 1 else GoodStream()

    monkeypatch.setattr(llm.httpx, "stream", fake_stream)
    monkeypatch.setattr(llm, "_sleep_before_retry", lambda _a: None)

    assert list(llm.chat_stream([{"role": "user", "content": "hi"}])) == ["ok"]
    assert len(attempts) == 2
