"""Publishing a corpus must never take the live one down.

`vectorstore.reset()` drops and recreates the collection in place. Against the
embedded store rebuilt on every boot that is fine. Against a shared remote
cluster it deletes the corpus students are querying, and a rebuild that then
fails — bad snapshot, OOM, expired key — leaves the service with no corpus and
no way back except re-running the job that just failed.

These tests pin the replacement: build a versioned collection alongside whatever
is serving, verify it holds what was sent, and only then move the alias. They
run against qdrant-client's local mode, which implements collections and aliases
in-process, so the logic is exercised for real without a cluster.

What they do NOT prove is that Qdrant Cloud behaves identically — TLS, auth, and
the free tier's 0.5 vCPU node are not modelled here. That check belongs to the
first real deployment and is recorded as unverified in docs/DEPLOY_GEMMA4.md.
"""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from ritaj import config, vectorstore
from ritaj.config import settings

DIM = 4


@pytest.fixture
def store(monkeypatch):
    """An in-memory Qdrant standing in for the configured client."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(vectorstore, "client", lambda: client)
    monkeypatch.setattr(settings, "collection", "ritaj")
    monkeypatch.setattr(settings, "qdrant_alias", "ritaj_current")
    yield client
    client.close()


def _rows(n: int, prefix: str = "doc"):
    ids = [f"{prefix}-{i}" for i in range(n)]
    documents = [f"chunk {i}" for i in range(n)]
    embeddings = [[float(i), 0.0, 0.0, 1.0] for i in range(n)]
    metadatas = [{"source": f"{prefix}.md", "title": "T"} for _ in range(n)]
    return ids, documents, embeddings, metadatas


# --- naming -------------------------------------------------------------------
def test_version_becomes_a_safe_collection_name():
    assert vectorstore.versioned_name("2026-08-20") == "ritaj_2026-08-20"
    # A version string reaches this from a manifest; it must not be able to
    # smuggle a path or a separator into a collection name.
    assert "/" not in vectorstore.versioned_name("a/b")
    assert ".." not in vectorstore.versioned_name("..")
    with pytest.raises(ValueError):
        vectorstore.versioned_name("")


# --- the publication path ------------------------------------------------------
def test_publish_switches_the_alias_without_touching_the_live_collection(store):
    ids, docs, embs, metas = _rows(10, "v1")
    first = vectorstore.create_versioned("v1", DIM)
    vectorstore.upsert_into(first, ids, docs, embs, metas, batch_size=3)
    vectorstore.verify_count(first, 10)
    assert vectorstore.publish(first) is None          # nothing was live before
    assert vectorstore.current_alias_target() == first

    # Build the next version while v1 is serving.
    ids2, docs2, embs2, metas2 = _rows(4, "v2")
    second = vectorstore.create_versioned("v2", DIM)
    vectorstore.upsert_into(second, ids2, docs2, embs2, metas2)

    # v1 is untouched and still readable throughout.
    assert store.count(first).count == 10
    assert vectorstore.current_alias_target() == first

    vectorstore.verify_count(second, 4)
    previous = vectorstore.publish(second)
    assert previous == first
    assert vectorstore.current_alias_target() == second
    # And the old collection still exists, which is what makes rollback cheap.
    assert store.collection_exists(first)
    assert store.count(first).count == 10


def test_rollback_is_another_alias_move(store):
    ids, docs, embs, metas = _rows(6, "v1")
    first = vectorstore.create_versioned("v1", DIM)
    vectorstore.upsert_into(first, ids, docs, embs, metas)
    vectorstore.publish(first)

    second = vectorstore.create_versioned("v2", DIM)
    vectorstore.upsert_into(second, *_rows(2, "v2"))
    vectorstore.publish(second)
    assert vectorstore.current_alias_target() == second

    # The bad corpus is withdrawn by pointing back, not by rebuilding.
    vectorstore.publish(first)
    assert vectorstore.current_alias_target() == first
    assert vectorstore.count() == 6


def test_reads_follow_the_alias(store):
    ids, docs, embs, metas = _rows(5, "v1")
    first = vectorstore.create_versioned("v1", DIM)
    vectorstore.upsert_into(first, ids, docs, embs, metas)
    vectorstore.publish(first)
    assert vectorstore.read_collection() == "ritaj_current"
    assert vectorstore.count() == 5

    hits = vectorstore.query([1.0, 0.0, 0.0, 1.0], k=3)
    assert len(hits) == 3
    assert all(cid.startswith("v1-") for cid, _ in hits)


def test_reads_fall_back_to_the_plain_name_without_an_alias(store, monkeypatch):
    monkeypatch.setattr(settings, "qdrant_alias", "")
    assert vectorstore.read_collection() == "ritaj"


# --- the guards ----------------------------------------------------------------
def test_a_short_collection_is_never_published(store):
    """A partial import that returned no error is the failure this catches."""
    name = vectorstore.create_versioned("v1", DIM)
    ids, docs, embs, metas = _rows(10, "v1")
    vectorstore.upsert_into(name, ids[:7], docs[:7], embs[:7], metas[:7])
    with pytest.raises(RuntimeError, match="holds 7 points, expected 10"):
        vectorstore.verify_count(name, 10)
    # Nothing was published, so there is still no alias target at all.
    assert vectorstore.current_alias_target() is None


def test_publishing_a_missing_collection_is_refused(store):
    with pytest.raises(RuntimeError, match="does not exist"):
        vectorstore.publish("ritaj_never_built")


def test_publishing_without_an_alias_is_refused(store, monkeypatch):
    monkeypatch.setattr(settings, "qdrant_alias", "")
    name = vectorstore.create_versioned("v1", DIM)
    with pytest.raises(RuntimeError, match="QDRANT_COLLECTION_ALIAS"):
        vectorstore.publish(name)


def test_batching_writes_every_point(store):
    """Bounded batches are for a 1 GB free-tier node; they must not lose rows."""
    ids, docs, embs, metas = _rows(37, "v1")
    name = vectorstore.create_versioned("v1", DIM)
    written = vectorstore.upsert_into(name, ids, docs, embs, metas, batch_size=5)
    assert written == 37
    vectorstore.verify_count(name, 37)


# --- configuration -------------------------------------------------------------
@pytest.mark.parametrize(
    ("mode", "path", "url", "expected"),
    [
        ("embedded", "/tmp/q", "", "embedded"),
        ("remote", "", "https://x.cloud.qdrant.io:6333", "remote"),
        # `auto` reproduces the historical rule so an upgrade does not move a
        # deployment's store out from under it.
        ("auto", "/tmp/q", "http://localhost:6333", "embedded"),
        ("auto", "", "http://localhost:6333", "remote"),
    ],
)
def test_mode_resolution(monkeypatch, mode, path, url, expected):
    monkeypatch.setattr(settings, "qdrant_mode", mode)
    monkeypatch.setattr(settings, "qdrant_path", path)
    monkeypatch.setattr(settings, "qdrant_url", url)
    assert config.qdrant_mode() == expected


def test_a_cloud_key_in_embedded_mode_is_refused(monkeypatch):
    """The silent failure this prevents looks exactly like an empty corpus."""
    monkeypatch.setattr(settings, "qdrant_mode", "embedded")
    monkeypatch.setattr(settings, "qdrant_path", "/tmp/q")
    monkeypatch.setattr(settings, "qdrant_api_key", "secret")
    problems = config.qdrant_problems()
    assert any("embedded" in p and "QDRANT_API_KEY" in p for p in problems)


def test_remote_without_a_url_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "qdrant_mode", "remote")
    monkeypatch.setattr(settings, "qdrant_url", "")
    assert any("QDRANT_URL" in p for p in config.qdrant_problems())


def test_remote_and_path_together_are_refused(monkeypatch):
    monkeypatch.setattr(settings, "qdrant_mode", "remote")
    monkeypatch.setattr(settings, "qdrant_url", "https://x.cloud.qdrant.io:6333")
    monkeypatch.setattr(settings, "qdrant_path", "/tmp/leftover")
    assert any("QDRANT_PATH" in p for p in config.qdrant_problems())


def test_production_remote_requires_tls_and_a_key(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "qdrant_mode", "remote")
    monkeypatch.setattr(settings, "qdrant_path", "")
    monkeypatch.setattr(settings, "qdrant_url", "http://plain.example.com:6333")
    monkeypatch.setattr(settings, "qdrant_api_key", "")
    problems = config.qdrant_problems()
    assert any("https" in p for p in problems)
    assert any("QDRANT_API_KEY" in p for p in problems)


def test_an_error_message_never_quotes_the_cluster_url(monkeypatch):
    """A Qdrant Cloud URL identifies the cluster; only the scheme is echoed."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "qdrant_mode", "remote")
    monkeypatch.setattr(settings, "qdrant_path", "")
    monkeypatch.setattr(settings, "qdrant_url", "http://secret-cluster-id.cloud.qdrant.io:6333")
    monkeypatch.setattr(settings, "qdrant_api_key", "")
    joined = " ".join(config.qdrant_problems())
    assert "secret-cluster-id" not in joined
    assert "'http'" in joined


def test_an_invalid_mode_is_named(monkeypatch):
    monkeypatch.setattr(settings, "qdrant_mode", "cloud")
    assert any("QDRANT_MODE" in p for p in config.qdrant_problems())


def test_the_client_refuses_a_contradictory_configuration(monkeypatch):
    """Fail at the seam rather than connecting to the wrong store."""
    vectorstore.client.cache_clear()
    monkeypatch.setattr(settings, "qdrant_mode", "embedded")
    monkeypatch.setattr(settings, "qdrant_path", "")
    with pytest.raises(RuntimeError, match="Qdrant configuration"):
        vectorstore.client()
    vectorstore.client.cache_clear()
