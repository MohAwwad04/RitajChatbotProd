"""Test-suite defaults, applied before anything imports `ritaj`.

`ritaj.config.Settings` reads the environment at class-definition time, so these
must be set before the first `from ritaj...` import anywhere in the suite —
which is exactly what a top-level conftest guarantees.

The suite is model-free by design (that is what makes it a CI gate rather than a
nightly job), so:

  * STARTUP_INIT=0 — creating the app must not kick off background
    initialization, which would load a ~2 GB embedder and build an index.
  * ENVIRONMENT=development — production is fail-closed on admin auth and CORS;
    individual tests opt into production explicitly to assert that behaviour.
"""

import os

os.environ.setdefault("STARTUP_INIT", "0")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("LLM_DAILY_BUDGET", "0")  # budget guard off unless a test sets it

import pytest  # noqa: E402


@pytest.fixture
def reset_readiness():
    """Give a test a clean lifecycle state and restore it afterwards."""
    from ritaj import readiness

    readiness.reset_for_tests()
    yield readiness
    readiness.reset_for_tests()
