"""Phase 9 — integration: corpus artifacts, cold start, and the SSE contract.

Model-free by construction: the corpus artifact is a directory on disk, so
restore and rollback can be exercised without embedding anything, and the
streaming contract is asserted against stubbed retrieval and generation.

What these cover that unit tests don't: the seams. A corpus artifact that
restores but whose CURRENT pointer wasn't updated, a production host that
silently falls into the slow build path, an SSE stream whose events arrive in an
order a published client doesn't expect.
"""

import json
from pathlib import Path

import pytest

from ritaj import bootstrap, corpus, ingest, readiness, source_policy
from ritaj.config import settings


# --- corpus artifacts --------------------------------------------------------
def _make_artifact(root: Path, version: str, *, chunks: int = 3,
                   source_id: str = "registration-instructions-ar") -> Path:
    """A published corpus artifact, as build_index.py --publish would write it."""
    directory = root / version
    (directory / "qdrant" / "collection").mkdir(parents=True)
    (directory / "qdrant" / "meta.json").write_text("{}", encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "version": version,
        "built_at": "2026-08-04T00:00:00+00:00",
        "documents": 1,
        "chunks": chunks,
        "sources_sha256": "abc123",
        "sources": [{"id": source_id, "canonical_url":
                     "https://ritaj.birzeit.edu/reg/instructions", "title": "t",
                     "language": "ar", "sha256": "abc", "fetched_at": "2026-08-01",
                     "effective_from": None, "effective_to": None,
                     "approved_by": "office"}],
    }), encoding="utf-8")
    with (directory / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for i in range(chunks):
            fh.write(json.dumps({
                "id": f"{source_id}-{i}",
                "text": f"chunk {i}",
                "metadata": {"source": source_id,
                             "url": "https://ritaj.birzeit.edu/reg/instructions",
                             "approved": True},
            }) + "\n")
    return directory


@pytest.fixture
def corpus_root(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    root.mkdir()
    monkeypatch.setattr(corpus, "CORPUS_ROOT", root)
    monkeypatch.setattr(corpus, "CURRENT_POINTER", root / "CURRENT")
    return root


def test_current_pointer_selects_the_served_corpus(corpus_root):
    _make_artifact(corpus_root, "20260804-aaaaaaaaaa")
    assert corpus.current_version() is None  # nothing published until CURRENT is set

    corpus.CURRENT_POINTER.write_text("20260804-aaaaaaaaaa\n", encoding="utf-8")
    assert corpus.current_version() == "20260804-aaaaaaaaaa"
    assert corpus.summary()["chunks"] == 3


def test_corpus_rollback_is_a_pointer_change(corpus_root):
    """The documented rollback: point CURRENT at the previous version."""
    _make_artifact(corpus_root, "20260801-old", chunks=2)
    _make_artifact(corpus_root, "20260804-new", chunks=9)

    corpus.CURRENT_POINTER.write_text("20260804-new", encoding="utf-8")
    assert corpus.summary()["chunks"] == 9

    corpus.CURRENT_POINTER.write_text("20260801-old", encoding="utf-8")
    assert corpus.current_version() == "20260801-old"
    assert corpus.summary()["chunks"] == 2
    # The rolled-forward artifact is still on disk, so rolling back is reversible.
    assert (corpus_root / "20260804-new").is_dir()


def test_a_dangling_pointer_is_reported_not_crashed(corpus_root):
    corpus.CURRENT_POINTER.write_text("20260804-missing", encoding="utf-8")
    assert corpus.current_version() == "20260804-missing"
    assert corpus.artifact_dir() is None
    assert corpus.manifest() is None
    assert corpus.summary()["chunks"] is None


def test_restore_copies_the_artifact_into_writable_storage(corpus_root, tmp_path,
                                                           monkeypatch):
    _make_artifact(corpus_root, "20260804-aaaaaaaaaa")
    corpus.CURRENT_POINTER.write_text("20260804-aaaaaaaaaa", encoding="utf-8")

    target = tmp_path / "runtime-qdrant"
    monkeypatch.setattr(settings, "qdrant_path", str(target))
    monkeypatch.setattr(bootstrap.vectorstore, "close", lambda: None)

    result = bootstrap.restore_artifact()
    assert result["restored"] is True
    assert (target / "meta.json").is_file()
    assert (target / "collection").is_dir()


def test_restore_is_skipped_when_storage_is_already_populated(corpus_root, tmp_path,
                                                             monkeypatch):
    """A warm restart must not race the open store for its directory lock."""
    _make_artifact(corpus_root, "20260804-aaaaaaaaaa")
    corpus.CURRENT_POINTER.write_text("20260804-aaaaaaaaaa", encoding="utf-8")

    target = tmp_path / "runtime-qdrant"
    target.mkdir()
    (target / "existing.db").write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "qdrant_path", str(target))

    def must_not_close():  # pragma: no cover - asserts absence
        raise AssertionError("closed an open store for a restore that should be skipped")

    monkeypatch.setattr(bootstrap.vectorstore, "close", must_not_close)
    assert bootstrap.restore_artifact()["restored"] is False


def test_restore_is_a_no_op_for_a_remote_qdrant(monkeypatch):
    """With a Qdrant server the index lives in the server, not in a directory."""
    monkeypatch.setattr(settings, "qdrant_path", "")
    assert bootstrap.restore_artifact() is None


# --- cold start --------------------------------------------------------------
def test_production_refuses_the_slow_build_path(monkeypatch, corpus_root):
    """Building at boot is what killed the deployment; production must not."""
    monkeypatch.setattr(settings, "qdrant_path", "")
    monkeypatch.setattr(bootstrap, "_store_populated", lambda: False)

    with pytest.raises(RuntimeError, match="index building is disabled"):
        bootstrap.initialize(allow_build=False)


def test_initialization_failure_is_explicit_about_the_fix(monkeypatch, corpus_root):
    monkeypatch.setattr(settings, "qdrant_path", "")
    monkeypatch.setattr(bootstrap, "_store_populated", lambda: False)
    with pytest.raises(RuntimeError) as exc:
        bootstrap.initialize(allow_build=False)
    message = str(exc.value)
    assert "build_index.py" in message and "--publish" in message


def test_readiness_transitions_starting_to_ready(reset_readiness):
    assert reset_readiness.state() == "starting"
    reset_readiness.start_background_init(lambda: {"chunks": 12})
    assert reset_readiness.wait_ready(timeout=5)
    snapshot = reset_readiness.snapshot()
    assert snapshot["state"] == "ready"
    assert snapshot["detail"]["chunks"] == 12
    assert "index_ready" in snapshot["timings_ms"]


def test_a_second_initializer_is_not_started_while_one_runs(reset_readiness):
    import threading

    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow():
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return {}

    reset_readiness.start_background_init(slow)
    assert started.wait(timeout=5)
    reset_readiness.start_background_init(slow)  # must be ignored
    release.set()
    reset_readiness.wait_ready(timeout=5)
    assert len(calls) == 1


# --- ingestion refuses to index what policy forbids --------------------------
def test_ingest_refuses_an_unapproved_record(monkeypatch):
    source, _ = source_policy.parse({
        "id": "pending-one",
        "canonical_url": "https://ritaj.birzeit.edu/reg/instructions",
        "title": "Pending", "language": "en", "visibility": "public",
        "content_kind": "html", "owner": "registration-office",
        "refresh": "weekly", "approved": False,
    })
    with pytest.raises(ValueError, match="unapproved"):
        ingest.build_from_sources([source])


def test_development_folder_ingestion_is_refused_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="development path"):
        ingest.build_from_directory("data/quarantine")


def test_build_index_refuses_in_production_with_no_approved_sources(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(source_policy, "load_and_validate",
                        lambda *a, **k: source_policy.ManifestReport([], [], []))
    with pytest.raises(RuntimeError, match="production index cannot be built"):
        ingest.build_index()


# --- SSE contract ------------------------------------------------------------
def _events(body: str) -> list[dict]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Retrieval + generation stubbed so the event contract can be asserted."""
    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.generate.condense", lambda m, h: m)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [
        ("Registration opens in week one.", {
            "source": "registration-instructions-ar", "title": "Registration",
            "url": "https://ritaj.birzeit.edu/reg/instructions",
            "as_of": "2026-08-01", "refresh": "weekly", "language": "en",
            "approved": True, "effective_from": "", "effective_to": "",
        }),
    ])
    monkeypatch.setattr("ritaj.api.answer_stream",
                        lambda *a, **k: iter(["Registration ", "opens in week one [1]."]))
    monkeypatch.setattr("ritaj.grounding.check",
                        lambda *a, **k: {"verdict": "grounded", "n_claims": 1,
                                         "uncited_claims": 0})


def test_stream_event_order_is_the_documented_contract(stub_pipeline):
    from starlette.testclient import TestClient

    from ritaj.api import app

    with TestClient(app) as client:
        response = client.post("/v2/chat/stream",
                               json={"message": "how do I register?"})
    events = _events(response.text)
    types = [e["type"] for e in events]

    assert types[0] == "sources", "citations must be known before any token"
    assert "token" in types
    assert types.index("grounding") > max(i for i, t in enumerate(types) if t == "token")
    assert types.index("links") > types.index("grounding")
    assert types[-1] == "done"
    assert events[-1]["request_id"]


def test_sources_event_carries_provenance(stub_pipeline):
    from starlette.testclient import TestClient

    from ritaj.api import app

    with TestClient(app) as client:
        response = client.post("/v2/chat/stream", json={"message": "how do I register?"})
    sources = next(e for e in _events(response.text) if e["type"] == "sources")["sources"]
    assert sources[0]["url"] == "https://ritaj.birzeit.edu/reg/instructions"
    assert sources[0]["as_of"] == "2026-08-01"


def test_abstention_costs_no_llm_call(monkeypatch):
    """Nothing above the relevance floor: refuse before spending quota."""
    from starlette.testclient import TestClient

    from ritaj.api import app

    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)
    monkeypatch.setattr("ritaj.api.generate.condense", lambda m, h: m)
    monkeypatch.setattr("ritaj.api.retrieve", lambda *a, **k: [])

    def must_not_generate(*a, **k):  # pragma: no cover - asserts absence
        raise AssertionError("called the model with no sources")

    monkeypatch.setattr("ritaj.api.answer_stream", must_not_generate)

    with TestClient(app) as client:
        response = client.post("/v2/chat/stream",
                               json={"message": "what is the capital of Japan?"})
    events = _events(response.text)
    assert events[0]["type"] == "blocked"
    assert events[0]["category"] == "no_sources"
    assert events[-1]["type"] == "done"


def test_blocked_request_never_reaches_retrieval(monkeypatch):
    from starlette.testclient import TestClient

    from ritaj.api import app

    monkeypatch.setattr("ritaj.api._require_ready", lambda: None)

    def must_not_retrieve(*a, **k):  # pragma: no cover - asserts absence
        raise AssertionError("retrieved for a blocked request")

    monkeypatch.setattr("ritaj.api.retrieve", must_not_retrieve)

    with TestClient(app) as client:
        response = client.post("/v2/chat/stream", json={"message": "What is my GPA?"})
    events = _events(response.text)
    assert events[0]["type"] == "blocked"
    assert events[0]["category"] == "personal_data"


def test_unknown_event_types_are_forward_compatible():
    """The contract says clients ignore unknown types; the panel's switch does."""
    source = (Path(__file__).resolve().parents[1]
              / "chrome-extension" / "sidepanel.js").read_text(encoding="utf-8")
    assert "default: break" in source, (
        "the SSE switch must have a default arm so a new server event type "
        "cannot break a published extension"
    )
