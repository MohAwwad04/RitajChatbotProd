"""Phase 4 — the public API is safe for a free quota and an unknown internet.

Before this, the chat endpoint had no rate limit, `allow_origins=["*"]`, raw
exception text streamed to the browser, and a chat log that stored every
question verbatim. Each test below is one of those.
"""

import json

import pytest

from ritaj import budget, config, errors, ratelimit, redact
from ritaj.config import settings


def _client():
    from starlette.testclient import TestClient

    from ritaj.api import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_limits():
    ratelimit.reset_for_tests()
    budget.reset_for_tests()
    yield
    ratelimit.reset_for_tests()
    budget.reset_for_tests()


# --- rate limiting -----------------------------------------------------------
def test_bucket_key_never_contains_the_address():
    key = ratelimit.bucket_key("192.0.2.55", "session-abc")
    assert "192.0.2.55" not in key
    assert "session-abc" not in key
    assert len(key) == 16


def test_bucket_key_separates_callers():
    a = ratelimit.bucket_key("192.0.2.1", "s1")
    b = ratelimit.bucket_key("192.0.2.2", "s1")
    c = ratelimit.bucket_key("192.0.2.1", "s2")
    assert len({a, b, c}) == 3


def test_bucket_key_is_stable_within_a_day():
    assert ratelimit.bucket_key("192.0.2.1", "s") == ratelimit.bucket_key("192.0.2.1", "s")


def test_limiter_refuses_after_the_window_allowance():
    limiter = ratelimit.SlidingWindowLimiter([ratelimit.Window(60, 3, "per-minute")])
    for _ in range(3):
        allowed, _, _ = limiter.check("k")
        assert allowed
    allowed, retry_after, window = limiter.check("k")
    assert allowed is False
    assert window == "per-minute"
    assert 0 < retry_after <= 61


def test_limiter_keeps_callers_independent():
    limiter = ratelimit.SlidingWindowLimiter([ratelimit.Window(60, 1, "per-minute")])
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is True
    assert limiter.check("a")[0] is False


def test_chat_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    ratelimit.reset_for_tests()
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])

    with _client() as c:
        body = {"message": "how do I register?", "session_id": "s1"}
        assert c.post("/chat", json=body).status_code == 200
        assert c.post("/chat", json=body).status_code == 200
        blocked = c.post("/chat", json=body)

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert int(blocked.headers["Retry-After"]) > 0


# --- daily budget ------------------------------------------------------------
def test_budget_trips_before_the_provider_does(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_budget", 2)
    budget.reset_for_tests()

    budget.check()
    budget.consume()
    budget.check()
    budget.consume()
    with pytest.raises(errors.PublicError) as exc:
        budget.check()

    assert exc.value.code == "LLM_BUDGET_EXHAUSTED"
    assert exc.value.retry_after > 0
    assert budget.snapshot()["remaining"] == 0


def test_budget_disabled_by_zero(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_budget", 0)
    budget.reset_for_tests()
    for _ in range(50):
        budget.consume()
    budget.check()  # must not raise


# --- concurrency -------------------------------------------------------------
def test_concurrency_cap_refuses_when_full():
    cap = ratelimit.ConcurrencyCap(limit=1, timeout=0.05)
    with cap:
        assert cap.active == 1
        with pytest.raises(errors.PublicError) as exc:
            with cap:
                pass
    assert exc.value.code == "BUSY"
    assert cap.active == 0


# --- request size ------------------------------------------------------------
def test_oversized_body_is_refused_before_parsing(monkeypatch):
    monkeypatch.setattr(settings, "max_body_bytes", 200)
    with _client() as c:
        r = c.post("/chat", json={"message": "x" * 5000})
    assert r.status_code == 413
    assert r.json()["code"] == "REQUEST_TOO_LARGE"


def test_every_response_carries_a_request_id():
    with _client() as c:
        r = c.get("/live")
    assert len(r.headers["X-Request-ID"]) == 16


# --- CORS --------------------------------------------------------------------
def test_development_allows_any_origin(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "cors_origins", [])
    monkeypatch.setattr(settings, "extension_id", "")
    assert config.allowed_origins() == ["*"]


def test_production_resolves_an_explicit_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "cors_origins", ["https://ritaj-assistant.example"])
    monkeypatch.setattr(settings, "extension_id", "abcdefghijklmnopabcdefghijklmnop")
    origins = config.allowed_origins()
    assert "*" not in origins
    assert "chrome-extension://abcdefghijklmnopabcdefghijklmnop" in origins


# --- fail-closed production --------------------------------------------------
def test_production_refuses_to_start_without_admin_auth_or_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_users", "")
    monkeypatch.setattr(settings, "admin_token", "")
    monkeypatch.setattr(settings, "cors_origins", [])
    monkeypatch.setattr(settings, "extension_id", "")
    monkeypatch.setattr(settings, "llm_api_key", "ollama")

    problems = config.check_production_config()
    joined = " ".join(problems)
    assert "admin authentication" in joined
    assert "CORS_ORIGINS" in joined
    assert "LLM_API_KEY" in joined


def test_development_has_no_production_requirements(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    assert config.check_production_config() == []


def test_app_refuses_to_start_when_production_is_misconfigured(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_users", "")
    monkeypatch.setattr(settings, "admin_token", "")
    with pytest.raises(RuntimeError, match="refusing to start"):
        with _client():
            pass


# --- error redaction ---------------------------------------------------------
def test_stream_error_event_carries_a_code_not_a_traceback(monkeypatch):
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve",
                        lambda *a, **k: [("Registration info.", {"title": "reg", "source": "reg"})])
    monkeypatch.setattr("ritaj.api.generate.condense", lambda m, h: m)

    def explode(*a, **k):
        raise errors.LLM_UNAVAILABLE(
            detail="HTTP 401 from accounts/SECRET-ACCOUNT-ID/ai/v1"
        )
        yield  # pragma: no cover

    monkeypatch.setattr("ritaj.api.answer_stream", explode)

    with _client() as c:
        r = c.post("/chat/stream", json={"message": "how do I register?"})
    body = r.text

    assert "SECRET-ACCOUNT-ID" not in body
    assert "Traceback" not in body
    assert '"code": "LLM_UNAVAILABLE"' in body
    events = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    assert events[-1]["type"] == "done"
    assert events[-1]["request_id"]


# --- v2 contract -------------------------------------------------------------
def test_v2_routes_exist_alongside_v1():
    from ritaj.api import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert {"/chat", "/chat/stream", "/v2/chat", "/v2/chat/stream"} <= paths


def test_v2_accepts_the_documented_request_shape(monkeypatch):
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])
    with _client() as c:
        r = c.post("/v2/chat", json={
            "message": "Open course registration",
            "history": [],
            "session_id": "random-local-uuid",
            "client": "chrome-extension",
            "locale": "en",
            "current_ritaj_path": "/register/",
        })
    assert r.status_code == 200


# --- redaction ---------------------------------------------------------------
@pytest.mark.parametrize("raw,gone", [
    ("my ID is 1191234", "1191234"),
    ("email a.student@student.birzeit.edu", "a.student@student.birzeit.edu"),
    ("call +970-2-2982057", "2982057"),
    ("token hf_abcdefghijklmnopqrstuvwxyz012345", "hf_abcdefghijklmnopqrstuvwxyz012345"),
    ("password: hunter2000", "hunter2000"),
])
def test_redaction_removes_identifiers(raw, gone):
    assert gone not in redact.text(raw)


def test_redaction_keeps_the_sentence_readable():
    out = redact.text("My ID is 1191234 and I can't register")
    assert "[id]" in out
    assert "can't register" in out


def test_ip_coarsening():
    assert redact.ip("192.0.2.55") == "192.0.x.x"
    assert redact.ip("2001:db8:abcd:1234::1").endswith("::/48")
    assert redact.ip(None) is None


def test_headers_drop_credentials():
    out = redact.headers({"Authorization": "Bearer secret", "Accept": "application/json"})
    assert out["Authorization"] == "[redacted]"
    assert out["Accept"] == "application/json"
