"""Phase 7 — the LLM client works against the providers it claims to support.

The migration from Groq to Cloudflare Workers AI is "just configuration"
*because* both speak OpenAI Chat Completions. That claim needs testing, not
asserting: providers differ in how they frame streams, what they put in an error
body, and what they do under load. These tests mock each provider's actual wire
shape so a contract break is caught here rather than in front of students.

No network: every test drives httpx through a stub.
"""

import json

import httpx
import pytest

from ritaj import errors, llm
from ritaj.config import settings

# --- provider wire shapes ----------------------------------------------------
# Cloudflare's OpenAI-compatible endpoint and Ollama both emit these, but they
# differ in detail: Cloudflare sends a `usage` block on the final chunk and
# terminates with `[DONE]`; Ollama omits usage and may send a chunk with an
# empty delta before finishing.
CLOUDFLARE_STREAM = [
    'data: {"choices":[{"delta":{"role":"assistant"},"index":0}]}',
    'data: {"choices":[{"delta":{"content":"Registration "},"index":0}]}',
    'data: {"choices":[{"delta":{"content":"opens in week one."},"index":0}]}',
    'data: {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}],'
    '"usage":{"prompt_tokens":812,"completion_tokens":9}}',
    "data: [DONE]",
]

OLLAMA_STREAM = [
    'data: {"choices":[{"delta":{"content":"Registration "}}]}',
    'data: {"choices":[{"delta":{"content":"opens in week one."}}]}',
    'data: {"choices":[{"delta":{"content":""}}]}',
    "data: [DONE]",
]


class _Stream:
    def __init__(self, lines, status=200, body=""):
        self.lines = lines
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status}",
                request=httpx.Request("POST", "http://provider/chat/completions"),
                response=httpx.Response(self.status, text=self.body),
            )

    def iter_lines(self):
        yield from self.lines


@pytest.fixture(autouse=True)
def _fresh_breaker(monkeypatch):
    llm._breaker = llm._CircuitBreaker()
    monkeypatch.setattr(llm, "_sleep_before_retry", lambda _a: None)
    yield
    llm._breaker = llm._CircuitBreaker()


@pytest.mark.parametrize("lines,name", [
    (CLOUDFLARE_STREAM, "cloudflare workers ai"),
    (OLLAMA_STREAM, "ollama"),
])
def test_streaming_contract_holds_for_each_provider(monkeypatch, lines, name):
    monkeypatch.setattr(llm.httpx, "stream", lambda *a, **k: _Stream(lines))
    out = "".join(llm.chat_stream([{"role": "user", "content": "when?"}]))
    assert out == "Registration opens in week one.", name


def test_request_targets_the_configured_endpoint(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(settings, "llm_base_url",
                        "https://api.cloudflare.com/client/v4/accounts/ACC/ai/v1")
    monkeypatch.setattr(settings, "llm_model", "@cf/google/gemma-4-26b-a4b-it")
    monkeypatch.setattr(settings, "llm_api_key", "cf-token")
    monkeypatch.setattr(llm.runtime_config, "get",
                        lambda k: "" if k == "llm_model" else
                        (0.2 if k == "temperature" else 1024))
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    llm.chat([{"role": "user", "content": "hi"}])

    assert captured["url"] == (
        "https://api.cloudflare.com/client/v4/accounts/ACC/ai/v1/chat/completions"
    )
    assert captured["headers"]["Authorization"] == "Bearer cf-token"
    assert captured["json"]["model"] == "@cf/google/gemma-4-26b-a4b-it"


def test_base_url_trailing_slash_does_not_double_up(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "llm_base_url", "https://provider.test/v1/")
    monkeypatch.setattr(llm.httpx, "post", lambda url, **k: (
        captured.setdefault("url", url),
        httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]},
                       request=httpx.Request("POST", url)),
    )[1])
    llm.chat([{"role": "user", "content": "hi"}])
    assert captured["url"] == "https://provider.test/v1/chat/completions"


# --- provider failure modes --------------------------------------------------
@pytest.mark.parametrize("status,retryable", [
    (429, True),    # quota / throttling
    (500, True),    # provider fault
    (502, True),
    (503, True),
    (504, True),
    (400, False),   # our request is wrong; retrying spends quota twice
    (401, False),   # bad token
    (404, False),   # wrong model id
])
def test_only_transient_statuses_are_retried(monkeypatch, status, retryable):
    attempts = []

    def fake_post(url, **kw):
        attempts.append(status)
        return httpx.Response(status, text="provider says no",
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(errors.PublicError):
        llm.chat([{"role": "user", "content": "hi"}])
    assert len(attempts) == (2 if retryable else 1)


def test_a_provider_error_body_never_reaches_the_student(monkeypatch):
    """Provider bodies can echo the prompt back."""
    body = json.dumps({"errors": [{"message": "prompt was: my student id is 1191234"}]})
    monkeypatch.setattr(llm.httpx, "post", lambda url, **k: httpx.Response(
        400, text=body, request=httpx.Request("POST", url)))

    with pytest.raises(errors.PublicError) as exc:
        llm.chat([{"role": "user", "content": "hi"}])

    assert "1191234" not in exc.value.public()["message"]
    assert "1191234" in exc.value.detail  # operators still get it


def test_malformed_stream_chunks_are_skipped_not_fatal(monkeypatch):
    lines = [
        "data: {not json at all",
        'data: {"choices":[]}',                       # no delta
        'data: {"choices":[{"delta":{}}]}',           # empty delta
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: [DONE]",
    ]
    monkeypatch.setattr(llm.httpx, "stream", lambda *a, **k: _Stream(lines))
    assert "".join(llm.chat_stream([{"role": "user", "content": "hi"}])) == "ok"


def test_a_timeout_is_reported_as_its_own_code(monkeypatch):
    def fake_post(url, **kw):
        raise httpx.ReadTimeout("provider stalled")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(errors.PublicError) as exc:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc.value.code == "LLM_TIMEOUT"


def test_stream_that_dies_before_any_token_is_retried(monkeypatch):
    attempts = []

    def fake_stream(method, url, **kw):
        attempts.append(1)
        if len(attempts) == 1:
            return _Stream([], status=503, body="cold start")
        return _Stream(CLOUDFLARE_STREAM)

    monkeypatch.setattr(llm.httpx, "stream", fake_stream)
    out = "".join(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert out == "Registration opens in week one."
    assert len(attempts) == 2


def test_timeouts_are_split_between_connect_and_read():
    """A hung connect should fail fast; a slow generation gets its full budget."""
    assert llm._TIMEOUT.connect <= 10
    assert llm._TIMEOUT.read >= 60


def test_configuration_check_rejects_a_hosted_endpoint_without_a_key(monkeypatch):
    from ritaj import bootstrap

    monkeypatch.setattr(settings, "llm_base_url", "https://api.cloudflare.com/x/ai/v1")
    monkeypatch.setattr(settings, "llm_api_key", "")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        bootstrap._check_llm_config()


def test_configuration_check_allows_a_local_endpoint_without_a_key(monkeypatch):
    from ritaj import bootstrap

    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "gemma4:e2b")
    assert bootstrap._check_llm_config()["hosted"] is False


# --- reasoning models -------------------------------------------------------
#
# @cf/google/gemma-4-26b-a4b-it emits `reasoning_content` before `content`, and
# those tokens bill as output. Measured 2026-08-20 on a RAG-shaped call:
# reasoning was ~70% of the output (200 of 285 tokens). Two consequences the
# code has to handle, both verified against the live provider before being
# written down here.

def test_an_empty_answer_is_refused_not_returned(monkeypatch):
    """A budget spent entirely on reasoning is a config fault, not an answer.

    Returning "" would reach the grounding checks, which would judge it an
    ungrounded response — reporting a retrieval-quality problem for what is
    actually a max_tokens that is too small.
    """
    import httpx

    from ritaj import errors, llm

    body = {
        "choices": [{
            "finish_reason": "length",
            "message": {"role": "assistant", "content": "",
                        "reasoning_content": "Let me think about this..."},
        }],
        "usage": {"prompt_tokens": 24, "completion_tokens": 60, "neurons": 1.85},
    }
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, json=body, request=httpx.Request("POST", "http://x")),
    )
    with pytest.raises(errors.PublicError) as excinfo:
        llm.chat([{"role": "user", "content": "hi"}], max_tokens=60)
    assert excinfo.value.code == "LLM_UNAVAILABLE"
    assert "reasoning" in (excinfo.value.detail or "")


def test_the_call_is_still_metered_when_it_produces_nothing(monkeypatch):
    """An unbilled failure is how a daily budget quietly stops binding."""
    import httpx

    from ritaj import budget, errors, llm

    before = budget.snapshot()["neurons_used"]

    body = {
        "choices": [{
            "finish_reason": "length",
            "message": {"role": "assistant", "content": "",
                        "reasoning_content": "thinking"},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 200, "neurons": 6.36},
    }
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, json=body, request=httpx.Request("POST", "http://x")),
    )
    with pytest.raises(errors.PublicError):
        llm.chat([{"role": "user", "content": "hi"}], max_tokens=200)
    after = budget.snapshot()["neurons_used"]
    assert after > before, "a call that produced no answer was not charged"


def test_the_providers_own_neuron_figure_wins(monkeypatch):
    """The local formula is insurance, not the source of truth.

    It was checked against Cloudflare on 2026-08-20 and reproduces the reported
    value to eight decimal places. Preferring the reported number means a
    pricing change cannot silently make the constants wrong.
    """
    from ritaj import budget

    # snapshot() rounds to 1dp, so differences of snapshots carry up to 0.1 of
    # rounding error. Read the accumulator directly — this test is specifically
    # about accounting precision, which is the one thing the rounded view loses.
    def used() -> float:
        with budget._lock:
            return budget._neurons

    before = used()
    # A figure deliberately unlike anything the formula would produce, so a pass
    # cannot come from the fallback happening to agree.
    budget.record(100, 200, reported_neurons=999.0)
    assert abs((used() - before) - 999.0) < 1e-6

    before = used()
    budget.record(100, 200)          # no reported value -> fall back to the formula
    assert abs((used() - before) - budget.neurons_for(100, 200)) < 1e-6
