"""Phase 4 — the public API is safe for a free quota and an unknown internet.

Before this, the chat endpoint had no rate limit, `allow_origins=["*"]`, raw
exception text streamed to the browser, and a chat log that stored every
question verbatim. Each test below is one of those.
"""

import json
import re
from pathlib import Path

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
def test_bucket_keys_never_contain_the_identifier():
    net = ratelimit.network_key("192.0.2.55")
    sess = ratelimit.session_key("session-abc")
    assert "192.0.2.55" not in net
    assert "session-abc" not in sess
    assert len(net) == 16 and len(sess) == 16


def test_network_and_session_keyspaces_are_separate():
    """The same string in either role must not collide into one bucket."""
    assert ratelimit.network_key("x") != ratelimit.session_key("x")


def test_bucket_keys_are_stable_within_a_day():
    assert ratelimit.network_key("192.0.2.1") == ratelimit.network_key("192.0.2.1")
    assert ratelimit.session_key("s") == ratelimit.session_key("s")


def test_distinct_addresses_get_distinct_buckets():
    assert ratelimit.network_key("192.0.2.1") != ratelimit.network_key("192.0.2.2")


@pytest.mark.parametrize("session_id", [None, "", "   ", "\x00", "x" * 200])
def test_malformed_session_ids_do_not_crash_or_exempt(session_id):
    """A client that declines to identify its conversation gets a bucket, not
    an exemption."""
    key = ratelimit.session_key(session_id)
    assert isinstance(key, str) and len(key) == 16


def test_missing_and_blank_session_ids_share_one_bucket():
    assert ratelimit.session_key(None) == ratelimit.session_key("")
    assert ratelimit.session_key("  ") == ratelimit.session_key(None)


# --- the bypass the combined bucket allowed ----------------------------------
def test_rotating_the_session_id_cannot_reset_the_network_limit(monkeypatch):
    """The original design hashed IP+session together, so a fresh session id
    produced a fresh bucket and an unlimited number of provider calls."""
    monkeypatch.setattr(settings, "network_rate_limit_per_minute", 5)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 100)  # session limit far away
    ratelimit.reset_for_tests()

    allowed = 0
    for i in range(50):
        try:
            ratelimit.check("198.51.100.7", f"freshly-minted-session-{i}")
            allowed += 1
        except errors.PublicError:
            break

    assert allowed == 5, f"session rotation obtained {allowed} calls, expected 5"


def test_one_runaway_session_is_stopped_before_the_network_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 3)
    monkeypatch.setattr(settings, "network_rate_limit_per_minute", 100)
    ratelimit.reset_for_tests()

    for _ in range(3):
        ratelimit.check("198.51.100.8", "one-session")
    with pytest.raises(errors.PublicError) as exc:
        ratelimit.check("198.51.100.8", "one-session")
    assert exc.value.code == "RATE_LIMITED"


def test_a_refused_request_does_not_consume_the_other_bucket(monkeypatch):
    """A request rejected by the session limiter must not also burn the network
    allowance — otherwise one noisy conversation degrades everyone on the NAT."""
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "network_rate_limit_per_minute", 10)
    ratelimit.reset_for_tests()

    ratelimit.check("203.0.113.9", "sess-a")            # 1 network, 1 session
    with pytest.raises(errors.PublicError):
        ratelimit.check("203.0.113.9", "sess-a")        # session refuses

    # A different session on the same network should still have 9 left, not 8.
    for i in range(9):
        ratelimit.check("203.0.113.9", f"sess-b{i}")
    with pytest.raises(errors.PublicError):
        ratelimit.check("203.0.113.9", "sess-c")


def test_separate_networks_do_not_interfere(monkeypatch):
    monkeypatch.setattr(settings, "network_rate_limit_per_minute", 2)
    ratelimit.reset_for_tests()
    ratelimit.check("192.0.2.1", "s1")
    ratelimit.check("192.0.2.1", "s1")
    with pytest.raises(errors.PublicError):
        ratelimit.check("192.0.2.1", "s1")
    ratelimit.check("192.0.2.2", "s1")  # a different campus, unaffected


# --- forwarded-header trust ---------------------------------------------------
class _FakeRequest:
    def __init__(self, peer, headers=None):
        self.client = type("C", (), {"host": peer})() if peer else None
        self.headers = headers or {}


def test_forwarded_header_is_ignored_by_default(monkeypatch):
    """X-Forwarded-For is client-settable; trusting it hands over the bucket key."""
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    request = _FakeRequest("10.0.0.5", {"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
    assert ratelimit.client_ip(request) == "10.0.0.5"


def test_forwarded_header_is_read_at_the_configured_depth(monkeypatch):
    """A conforming proxy APPENDS the address it saw, so with one trusted proxy
    and a client that sent no header of its own, the chain has exactly one entry
    and it is the real client."""
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    request = _FakeRequest("10.0.0.5", {"x-forwarded-for": "203.0.113.7"})
    assert ratelimit.client_ip(request) == "203.0.113.7"


def test_a_spoofed_prefix_cannot_choose_the_bucket(monkeypatch):
    """A client at 203.0.113.7 sends a forged header; the trusted proxy appends
    the address it actually observed. Everything to the left of that is the
    client's own invention and must not affect which bucket it lands in."""
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    honest = ratelimit.client_ip(_FakeRequest(
        "10.0.0.5", {"x-forwarded-for": "203.0.113.7"}))
    forged_one = ratelimit.client_ip(_FakeRequest(
        "10.0.0.5", {"x-forwarded-for": "9.9.9.9, 203.0.113.7"}))
    forged_many = ratelimit.client_ip(_FakeRequest(
        "10.0.0.5", {"x-forwarded-for": "1.1.1.1, 2.2.2.2, 3.3.3.3, 203.0.113.7"}))
    assert honest == forged_one == forged_many == "203.0.113.7"

    # And therefore the bucket is identical no matter what the client claims.
    assert (ratelimit.network_key(forged_one)
            == ratelimit.network_key(forged_many)
            == ratelimit.network_key(honest))


def test_two_trusted_proxies_read_two_hops_from_the_right(monkeypatch):
    """client -> P1 -> P2 -> us: P1 appends the client, P2 appends P1."""
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    request = _FakeRequest("10.0.0.2", {"x-forwarded-for": "203.0.113.7, 10.0.0.1"})
    assert ratelimit.client_ip(request) == "203.0.113.7"


def test_a_short_or_malformed_chain_falls_back_to_the_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert ratelimit.client_ip(
        _FakeRequest("10.0.0.5", {"x-forwarded-for": "203.0.113.7"})) == "10.0.0.5"
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert ratelimit.client_ip(
        _FakeRequest("10.0.0.5", {"x-forwarded-for": "not-an-ip"})) == "10.0.0.5"


def test_addressing_diagnostic_flags_a_proxy_with_no_trust_configured(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    request = _FakeRequest("10.0.0.5", {"x-forwarded-for": "203.0.113.7"})
    diagnostic = ratelimit.client_ip_diagnostics(request)
    assert diagnostic["ok"] is False
    assert "global" in diagnostic["reason"]


def test_addressing_diagnostic_is_clean_when_configured_correctly(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    request = _FakeRequest("10.0.0.5", {"x-forwarded-for": "203.0.113.7, 10.0.0.9"})
    assert ratelimit.client_ip_diagnostics(request)["ok"] is True


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
def test_neuron_conversion_matches_the_published_prices():
    """Cloudflare publishes $0.10/M input and $0.30/M output for Gemma 4 26B
    A4B, and bills neurons at $0.011/1000. A representative RAG request —
    4,000 input + 500 output — should therefore cost about 50 neurons, which is
    where "roughly 200 answers/day" on a 10,000 allowance comes from."""
    cost = budget.neurons_for(prompt_tokens=4_000, completion_tokens=500)
    assert 45 <= cost <= 55, cost
    assert 9_000 / cost == pytest.approx(180, rel=0.2)


def test_budget_trips_before_the_provider_does(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 100)
    budget.reset_for_tests()

    budget.check()
    budget.record(prompt_tokens=4_000, completion_tokens=500)   # ~50 neurons
    budget.check()
    budget.record(prompt_tokens=4_000, completion_tokens=500)   # ~100 neurons
    with pytest.raises(errors.PublicError) as exc:
        budget.check()

    assert exc.value.code == "LLM_BUDGET_EXHAUSTED"
    assert exc.value.retry_after > 0
    assert budget.snapshot()["neurons_remaining"] == 0


def test_a_short_call_costs_far_less_than_a_full_answer(monkeypatch):
    """The per-answer budget priced these identically, which is wrong by close
    to an order of magnitude."""
    condense = budget.neurons_for(prompt_tokens=300, completion_tokens=60)
    answer = budget.neurons_for(prompt_tokens=4_000, completion_tokens=500)
    assert answer > condense * 5


def test_budget_disabled_by_zero(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 0)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 0)
    budget.reset_for_tests()
    for _ in range(50):
        budget.record(4_000, 500)
    budget.check()  # must not raise


def test_optional_call_cap_is_enforced_independently(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 0)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 3)
    budget.reset_for_tests()
    for _ in range(3):
        budget.check()
        budget.record(1, 1)
    with pytest.raises(errors.PublicError):
        budget.check()


def test_usage_is_metered_at_the_provider_call(monkeypatch):
    """The bug this replaces: generate.condense() makes its own provider call,
    and per-answer accounting never counted it."""
    import httpx

    from ritaj import llm

    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 100_000)
    budget.reset_for_tests()
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: httpx.Response(
        200,
        json={"choices": [{"message": {"content": "ok"}}],
              "usage": {"prompt_tokens": 4_000, "completion_tokens": 500}},
        request=httpx.Request("POST", url),
    ))

    llm.chat([{"role": "user", "content": "hi"}])
    first = budget.snapshot()
    assert first["provider_calls"] == 1
    assert 45 <= first["neurons_used"] <= 55

    # A second call — a condense, say — is counted too, without its caller
    # having to remember.
    llm.chat([{"role": "user", "content": "rewrite this"}])
    assert budget.snapshot()["provider_calls"] == 2


def test_a_provider_without_usage_is_still_metered(monkeypatch):
    """Ollama reports no usage block. An unmetered path is how a budget quietly
    stops binding."""
    import httpx

    from ritaj import llm

    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 100_000)
    budget.reset_for_tests()
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: httpx.Response(
        200, json={"choices": [{"message": {"content": "a longer answer " * 50}}]},
        request=httpx.Request("POST", url),
    ))

    llm.chat([{"role": "user", "content": "x" * 4_000}])
    snapshot = budget.snapshot()
    assert snapshot["provider_calls"] == 1
    assert snapshot["neurons_used"] > 0


def test_streamed_usage_is_read_from_the_final_chunk(monkeypatch):
    """Cloudflare attaches usage to a final chunk whose delta has no content —
    so it must be read before the content check skips that chunk."""
    import httpx

    from ritaj import llm

    monkeypatch.setattr(settings, "llm_daily_neuron_budget", 100_000)
    budget.reset_for_tests()

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Registration"}}]}'
            yield ('data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
                   '"usage":{"prompt_tokens":4000,"completion_tokens":500}}')
            yield "data: [DONE]"

    monkeypatch.setattr(llm.httpx, "stream", lambda *a, **k: _Stream())
    assert "".join(llm.chat_stream([{"role": "user", "content": "hi"}])) == "Registration"

    snapshot = budget.snapshot()
    assert snapshot["provider_calls"] == 1
    assert 45 <= snapshot["neurons_used"] <= 55


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


def test_the_streaming_route_takes_a_generation_slot(monkeypatch):
    """The cap was applied to /chat but not to /chat/stream — the route the
    extension actually uses. A load test found it: eight simultaneous requests
    against a cap of two were all served.
    """
    monkeypatch.setattr(settings, "max_concurrent_generations", 1)
    monkeypatch.setattr(settings, "queue_timeout_seconds", 0.05)
    ratelimit.reset_for_tests()

    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])

    # Hold the only slot, so a request must be refused rather than queued.
    held = ratelimit.generation_slot()
    held.acquire()
    try:
        with _client() as c:
            response = c.post("/v2/chat/stream", json={"message": "how do I register?"})
    finally:
        held.release()

    assert response.status_code == 503
    assert response.json()["code"] == "BUSY"


def test_the_streaming_route_releases_its_slot(monkeypatch):
    """A leaked slot permanently shrinks capacity, one request at a time."""
    monkeypatch.setattr(settings, "max_concurrent_generations", 1)
    monkeypatch.setattr(settings, "queue_timeout_seconds", 0.05)
    ratelimit.reset_for_tests()

    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])

    with _client() as c:
        for _ in range(3):
            assert c.post("/v2/chat/stream", json={"message": "hi"}).status_code == 200
    assert ratelimit.generation_slot().active == 0


def test_a_refused_slot_is_a_clean_503_not_a_partial_stream(monkeypatch):
    """BUSY must arrive before the response starts. Acquiring inside the
    generator would emit it as an error event after the sources had already
    been rendered."""
    monkeypatch.setattr(settings, "max_concurrent_generations", 1)
    monkeypatch.setattr(settings, "queue_timeout_seconds", 0.05)
    ratelimit.reset_for_tests()
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])

    held = ratelimit.generation_slot()
    held.acquire()
    try:
        with _client() as c:
            response = c.post("/v2/chat/stream", json={"message": "hi"})
    finally:
        held.release()

    assert "data:" not in response.text, "a refused request still opened a stream"
    assert response.headers.get("Retry-After")


# --- request size ------------------------------------------------------------
def test_oversized_body_with_content_length_is_refused():
    """The honest oversized request: declared, and refused without reading it."""
    payload = {"message": "x" * 2000, "history": [
        {"role": "user", "content": "y" * 1900} for _ in range(30)
    ]}
    with _client() as c:
        response = c.post("/chat", json=payload)
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_oversized_chunked_body_is_refused():
    """The bypass the Content-Length check allowed.

    A chunked request declares no length, so a header check never fires and the
    body is buffered in full by whatever reads it next — a memory-exhaustion
    request against a 2-vCPU host. The cap now counts the bytes themselves.
    """
    oversized = b'{"message": "' + b"x" * (settings.max_body_bytes + 5_000) + b'"}'

    def chunks():
        for i in range(0, len(oversized), 4096):
            yield oversized[i:i + 4096]

    with _client() as c:
        response = c.post(
            "/chat",
            content=chunks(),  # no Content-Length: httpx sends chunked
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"


def test_an_ordinary_request_passes_the_body_cap(monkeypatch):
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])
    with _client() as c:
        response = c.post("/chat", json={"message": "how do I register?"})
    assert response.status_code == 200


def test_a_message_over_the_configured_limit_is_rejected():
    with _client() as c:
        response = c.post("/chat", json={"message": "x" * (settings.max_message_chars + 1)})
    assert response.status_code == 422


def test_a_message_at_the_configured_limit_is_accepted(monkeypatch):
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])
    with _client() as c:
        response = c.post("/chat", json={"message": "x" * settings.max_message_chars})
    assert response.status_code == 200


def test_a_history_turn_over_the_limit_is_rejected():
    with _client() as c:
        response = c.post("/chat", json={
            "message": "hi",
            "history": [{"role": "user", "content": "x" * (settings.max_message_chars + 1)}],
        })
    assert response.status_code == 422


def test_the_declared_limits_are_mutually_consistent():
    """Three sources once disagreed about how long a message may be:
    MAX_MESSAGE_CHARS said 2000 and was never read, the schema said 8000, and the
    extension had no limit at all."""
    from ritaj.api import ChatRequest

    # The message bound must come from the setting, not a literal in the schema.
    assert "max_length" not in (ChatRequest.model_fields["message"].metadata and
                                str(ChatRequest.model_fields["message"].metadata) or "")
    # A single message plus a full history must still fit inside the body cap,
    # or the schema would accept what the transport refuses.
    assert settings.max_message_chars < settings.max_body_bytes
    assert settings.history_max_chars <= settings.max_message_chars

    # The extension's declared limit must match the server's.
    config_js = (Path(__file__).resolve().parents[1]
                 / "chrome-extension" / "config.js").read_text(encoding="utf-8")
    match = re.search(r"MAX_MESSAGE_CHARS\s*=\s*(\d+)", config_js)
    assert match, "chrome-extension/config.js must declare MAX_MESSAGE_CHARS"
    assert int(match.group(1)) == settings.max_message_chars


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
    # Fabricated, never issued. secret-scan: allow
    ("token hf_abcdefghijklmnopqrstuvwxyz012345", "hf_abcdefghijklmnopqrstuvwxyz012345"),  # secret-scan: allow
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
