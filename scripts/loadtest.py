#!/usr/bin/env python3
"""Measure what this service can actually take, against a stub provider.

Roadmap Phase F3. The point is a *measured* capacity number rather than one
inferred from the provider's theoretical maximum: how many students can be
served at once, what they wait, and what happens at each limit.

The LLM is stubbed with a configurable delay. That is deliberate — this measures
the **application's** behaviour (concurrency cap, queue timeout, rate limits,
budget, error handling) without spending provider quota or letting network
variance drown the signal. Real provider latency is added on top and is measured
separately against staging (HANDBOOK.md §4).

Usage:
    python scripts/loadtest.py                    # full suite
    python scripts/loadtest.py --scenario burst
    python scripts/loadtest.py --json results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Must be set before ritaj.config is imported.
import os  # noqa: E402

os.environ.setdefault("STARTUP_INIT", "0")
os.environ.setdefault("ENVIRONMENT", "development")


@dataclass
class Outcome:
    status: int
    code: str | None
    seconds: float


@dataclass
class Result:
    name: str
    description: str
    requests: int = 0
    ok: int = 0
    by_code: dict = field(default_factory=dict)
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None
    notes: list[str] = field(default_factory=list)
    passed: bool = True

    def record(self, outcomes: list[Outcome]) -> None:
        self.requests = len(outcomes)
        self.ok = sum(1 for o in outcomes if o.status == 200)
        for outcome in outcomes:
            key = outcome.code or str(outcome.status)
            self.by_code[key] = self.by_code.get(key, 0) + 1
        times = sorted(o.seconds * 1000 for o in outcomes)
        if times:
            self.p50_ms = round(statistics.median(times), 1)
            self.p95_ms = round(times[min(len(times) - 1, int(len(times) * 0.95))], 1)
            self.max_ms = round(times[-1], 1)


def build_client(generation_delay: float = 0.05, fail: bool = False):
    """A TestClient stubbed at the HTTP layer, not at the application layer.

    Only `httpx.stream` is replaced, so everything above it runs for real:
    admission controls, the concurrency cap, generate.py's prompt assembly,
    llm.py's stream parsing and retry logic, and the budget metering that reads
    the provider's `usage` block. Stubbing `answer_stream` instead — the obvious
    shortcut — bypasses metering entirely and makes the budget scenario pass
    vacuously, which is exactly the kind of test that proves nothing.

    Retrieval and grounding are stubbed, because both need models.
    """
    from starlette.testclient import TestClient

    from ritaj import api, budget, llm, ratelimit

    passage = ("Registration opens in week one.", {
        "source": "registration-instructions-ar", "title": "Registration",
        "url": "https://ritaj.birzeit.edu/reg/instructions", "as_of": "2026-08-01",
        "refresh": "weekly", "language": "en", "approved": True,
        "effective_from": "", "effective_to": "",
    })

    api._require_ready = lambda: None
    api.retrieve = lambda *a, **k: [passage]
    api.grounding.check = lambda *a, **k: {
        "verdict": "grounded", "n_claims": 1, "uncited_claims": 0,
    }

    class _StubStream:
        def __enter__(self):
            # Holding the slot for a realistic interval is what makes the
            # concurrency cap and the queue timeout observable at all.
            time.sleep(generation_delay)
            return self

        def __exit__(self, *a):
            return False

        def raise_for_status(self):
            if fail:
                import httpx as _httpx

                raise _httpx.ConnectError("stubbed provider outage")

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Registration opens in week one [1]."}}]}'
            # Real usage numbers so the budget guard is exercised properly.
            yield ('data: {"choices":[{"delta":{}}],'
                   '"usage":{"prompt_tokens":4000,"completion_tokens":500}}')
            yield "data: [DONE]"

    llm.httpx.stream = lambda *a, **k: _StubStream()
    llm._sleep_before_retry = lambda _a: None
    llm._breaker = llm._CircuitBreaker()

    ratelimit.reset_for_tests()
    budget.reset_for_tests()
    return TestClient(api.app)


def raise_all_limits(settings) -> None:
    """Take the rate limiters out of the way for scenarios testing other limits.

    Every window, not just per-minute: raising only the minute limit and then
    firing 300 requests trips the per-hour one instead, which looks like a
    failure of whatever was actually under test.
    """
    for attribute in (
        "rate_limit_per_minute", "rate_limit_per_hour", "rate_limit_per_day",
        "network_rate_limit_per_minute", "network_rate_limit_per_hour",
        "network_rate_limit_per_day",
    ):
        setattr(settings, attribute, 1_000_000)


def fire(client, session: str, message: str = "how do I register?") -> Outcome:
    started = time.monotonic()
    try:
        response = client.post("/v2/chat/stream",
                               json={"message": message, "session_id": session})
        elapsed = time.monotonic() - started
        code = None
        if response.status_code != 200:
            try:
                code = response.json().get("code")
            except ValueError:
                code = None
        else:
            # A stream can carry an error event with a 200 status.
            for line in response.text.splitlines():
                if line.startswith("data:") and '"type": "error"' in line:
                    code = json.loads(line[5:]).get("code")
        return Outcome(response.status_code, code, elapsed)
    except Exception as exc:  # noqa: BLE001 — a crash is a result worth recording
        return Outcome(0, type(exc).__name__, time.monotonic() - started)


# --- scenarios ----------------------------------------------------------------
def scenario_sequential(settings) -> Result:
    result = Result("sequential", "One student, 20 questions in a row")
    raise_all_limits(settings)
    client = build_client()
    with client:
        result.record([fire(client, "seq") for _ in range(20)])
    result.passed = result.ok == result.requests
    return result


def scenario_concurrent(settings) -> Result:
    cap = settings.max_concurrent_generations
    result = Result("concurrent",
                    f"{cap * 4} simultaneous requests against a cap of {cap}")
    raise_all_limits(settings)
    settings.queue_timeout_seconds = 2.0
    client = build_client(generation_delay=0.2)
    with client, ThreadPoolExecutor(max_workers=cap * 4) as pool:
        outcomes = list(pool.map(lambda i: fire(client, f"c{i}"), range(cap * 4)))
    result.record(outcomes)
    # Everything should either be served or refused with BUSY — never hang,
    # never crash, never silently drop.
    unexpected = {k: v for k, v in result.by_code.items() if k not in ("200", "BUSY")}
    result.passed = not unexpected
    if unexpected:
        result.notes.append(f"unexpected outcomes: {unexpected}")
    result.notes.append(f"served {result.ok}, refused with BUSY "
                        f"{result.by_code.get('BUSY', 0)}")
    return result


def scenario_queue_timeout(settings) -> Result:
    result = Result("queue-timeout",
                    "Requests beyond the cap are refused, not queued forever")
    raise_all_limits(settings)
    settings.queue_timeout_seconds = 0.3
    client = build_client(generation_delay=1.5)
    cap = settings.max_concurrent_generations
    with client, ThreadPoolExecutor(max_workers=cap + 3) as pool:
        outcomes = list(pool.map(lambda i: fire(client, f"q{i}"), range(cap + 3)))
    result.record(outcomes)
    busy = result.by_code.get("BUSY", 0)
    result.passed = busy > 0 and (result.max_ms or 0) < 5_000
    result.notes.append(f"{busy} refused with BUSY; slowest {result.max_ms} ms "
                        "(a queue that never refuses would keep climbing)")
    return result


def scenario_session_rotation(settings) -> Result:
    result = Result("session-rotation",
                    "Minting a fresh session id must not reset the network limit")
    raise_all_limits(settings)
    settings.network_rate_limit_per_minute = 5
    client = build_client()
    with client:
        outcomes = [fire(client, f"rotated-{i}") for i in range(25)]
    result.record(outcomes)
    result.passed = result.ok == 5
    result.notes.append(f"served {result.ok} of 25 with a network limit of 5 "
                        "(the combined-bucket design served all 25)")
    return result


def scenario_budget(settings) -> Result:
    result = Result("budget", "Daily neuron budget stops spending predictably")
    raise_all_limits(settings)
    # The stub reports 4,000 in / 500 out per call, i.e. ~50 neurons. A budget
    # of 120 allows two answers and then must refuse.
    settings.llm_daily_neuron_budget = 120
    client = build_client()
    with client:
        outcomes = [fire(client, "budget") for _ in range(10)]
    result.record(outcomes)
    exhausted = result.by_code.get("LLM_BUDGET_EXHAUSTED", 0)
    result.passed = exhausted > 0
    result.notes.append(f"{exhausted} refused with LLM_BUDGET_EXHAUSTED once "
                        "the allowance was spent")
    settings.llm_daily_neuron_budget = 0
    return result


def scenario_provider_failure(settings) -> Result:
    result = Result("provider-failure",
                    "Provider errors surface as codes, and the circuit opens")
    raise_all_limits(settings)

    from ritaj import llm

    # Fails inside llm.py, so the real classification, retry and circuit-breaker
    # paths run rather than a pre-built exception being raised at the API layer.
    client = build_client(fail=True)
    with client:
        outcomes = [fire(client, "fail") for _ in range(6)]
    result.record(outcomes)
    result.passed = all(o.code == "LLM_UNAVAILABLE" for o in outcomes)
    result.notes.append("every failure returned a stable code, no traceback")
    result.notes.append(f"circuit breaker: {llm.circuit_state()}")
    llm._breaker = llm._CircuitBreaker()
    return result


def scenario_memory_soak(settings) -> Result:
    result = Result("soak", "300 requests without unbounded memory growth")
    raise_all_limits(settings)
    # Measuring memory, not spend. Left enabled, the real 9,000-neuron budget
    # refuses after ~180 answers — itself a useful confirmation that the
    # documented "roughly 200 answers/day" estimate matches the implementation.
    settings.llm_daily_neuron_budget = 0
    client = build_client()

    import gc
    import tracemalloc

    gc.collect()
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    with client:
        outcomes = [fire(client, f"soak-{i % 20}") for i in range(300)]
    gc.collect()
    peak_growth = (tracemalloc.get_traced_memory()[0] - baseline) / 1024 / 1024
    tracemalloc.stop()

    result.record(outcomes)
    # The rate limiter keeps per-key deques and the chat log appends; both are
    # bounded, so retained growth over 300 requests should be small.
    result.passed = result.ok == result.requests and peak_growth < 25
    result.notes.append(f"retained heap growth {peak_growth:.1f} MB over 300 requests")
    return result


SCENARIOS = {
    "sequential": scenario_sequential,
    "concurrent": scenario_concurrent,
    "queue": scenario_queue_timeout,
    "rotation": scenario_session_rotation,
    "budget": scenario_budget,
    "provider": scenario_provider_failure,
    "soak": scenario_memory_soak,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), action="append")
    ap.add_argument("--json", type=Path, help="write results here")
    args = ap.parse_args()

    from ritaj.config import settings

    chosen = args.scenario or list(SCENARIOS)
    results: list[Result] = []

    print("Load and resilience — application behaviour against a stub provider\n")
    for name in chosen:
        # Each scenario mutates limits; restore between runs so they are
        # independent rather than order-dependent.
        saved = {k: getattr(settings, k) for k in (
            "rate_limit_per_minute", "rate_limit_per_hour", "rate_limit_per_day",
            "network_rate_limit_per_minute", "network_rate_limit_per_hour",
            "network_rate_limit_per_day", "queue_timeout_seconds",
            "llm_daily_neuron_budget", "max_concurrent_generations",
        )}
        try:
            result = SCENARIOS[name](settings)
        finally:
            for key, value in saved.items():
                setattr(settings, key, value)
        results.append(result)

        mark = "PASS" if result.passed else "FAIL"
        print(f"  [{mark}] {result.name} — {result.description}")
        print(f"         {result.requests} req · {result.ok} ok · "
              f"p50 {result.p50_ms} ms · p95 {result.p95_ms} ms")
        if result.by_code:
            print(f"         outcomes: {result.by_code}")
        for note in result.notes:
            print(f"         {note}")
        print()

    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in results], indent=2),
                             encoding="utf-8")
        print(f"Wrote {args.json}")

    failed = [r.name for r in results if not r.passed]
    print(
        "\nThese are APPLICATION capacity numbers, measured against a stub "
        "provider.\nReal first-token and full-answer latency must be measured on "
        "staging against\nCloudflare before any capacity claim is made."
    )
    if failed:
        sys.exit(f"FAILED: {', '.join(failed)}")


if __name__ == "__main__":
    main()
