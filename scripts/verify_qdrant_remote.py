#!/usr/bin/env python3
"""Prove a remote Qdrant cluster actually works, before trusting it with a corpus.

The publication path in `ritaj.vectorstore` — versioned collection, count
verification, atomic alias switch, rollback — is covered by tests against
qdrant-client's LOCAL mode, which implements collections and aliases in-process.
That proves the logic. It does not prove that a real cluster behaves the same
over the wire, under TLS, with an API key, on a 0.5 vCPU / 1 GB free-tier node.

This script closes that gap by running the whole path against the configured
cluster and reporting what happened, including timings. It is the acceptance
check named in PRODUCTION_FREE_LIVE_PLAN.md section 9.

It is deliberately safe to run against a live cluster:

  * every collection it makes is prefixed `_verify_`, so it cannot collide with
    a real corpus collection (`ritaj_<version>`);
  * it uses its own alias, never QDRANT_COLLECTION_ALIAS, so a live alias is
    never repointed;
  * it deletes everything it created, including on failure.

Usage:
    set -a; source .env.local; set +a
    python scripts/verify_qdrant_remote.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ritaj import config  # noqa: E402
from ritaj.config import settings  # noqa: E402

# Small enough to be quick, large enough to force more than one upsert batch.
POINTS = 300
DIM = 8
BATCH = 64

PREFIX = "_verify_"


def _fmt(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms" if seconds < 1 else f"{seconds:.2f}s"


def main() -> int:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        CreateAlias,
        CreateAliasOperation,
        DeleteAlias,
        DeleteAliasOperation,
        Distance,
        PointStruct,
        VectorParams,
    )

    mode = config.qdrant_mode()
    problems = config.qdrant_problems()
    print("Configuration\n")
    print(f"  mode      : {mode}")
    # Never print the URL or the key: the host identifies the cluster and the
    # key is the credential. Scheme and a fingerprint are enough to diagnose.
    scheme = settings.qdrant_url.split("://", 1)[0] if "://" in settings.qdrant_url else "(none)"
    print(f"  scheme    : {scheme}")
    print(f"  api key   : {'set' if settings.qdrant_api_key else 'ABSENT'}")
    print(f"  timeout   : {settings.qdrant_timeout_seconds}s")
    for problem in problems:
        print(f"  ERROR     : {problem}")
    if problems:
        return 1
    if mode != "remote":
        print("\n  QDRANT_MODE is not 'remote' — nothing to verify here.")
        return 1

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=int(settings.qdrant_timeout_seconds),
        https=settings.qdrant_url.startswith("https://"),
    )

    stamp = f"{int(time.time())}{random.randint(100, 999)}"
    v1 = f"{PREFIX}{stamp}_v1"
    v2 = f"{PREFIX}{stamp}_v2"
    alias = f"{PREFIX}{stamp}_current"
    created: list[str] = []
    alias_made = False
    failures = 0

    def check(label: str, fn):
        nonlocal failures
        started = time.monotonic()
        try:
            result = fn()
            print(f"  PASS  {label} ({_fmt(time.monotonic() - started)})")
            return result
        except Exception as exc:  # noqa: BLE001 — this script reports, never raises
            print(f"  FAIL  {label}: {type(exc).__name__}: {exc}")
            failures += 1
            return None

    try:
        print("\nReachability\n")
        check("the cluster answers", lambda: client.get_collections())

        print("\nBuild a versioned collection\n")

        def build(name: str, count: int):
            client.create_collection(
                name, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE)
            )
            created.append(name)
            for start in range(0, count, BATCH):
                points = [
                    PointStruct(
                        id=i,
                        vector=[float((i + d) % 7) for d in range(DIM)],
                        payload={"chunk_id": f"{name}-{i}", "document": f"chunk {i}"},
                    )
                    for i in range(start, min(start + BATCH, count))
                ]
                client.upsert(name, points=points, wait=True)
            return name

        check(f"create + upsert {POINTS} points in batches of {BATCH}",
              lambda: build(v1, POINTS))
        check(f"count is exactly {POINTS}",
              lambda: _expect(client.count(v1).count, POINTS))

        print("\nPublish via an alias\n")

        def publish(target: str):
            nonlocal alias_made
            ops = []
            if alias_made:
                ops.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias)))
            ops.append(CreateAliasOperation(
                create_alias=CreateAlias(collection_name=target, alias_name=alias)))
            client.update_collection_aliases(change_aliases_operations=ops)
            alias_made = True
            return target

        check("alias points at v1", lambda: publish(v1))
        check("reading through the alias returns v1's points",
              lambda: _expect(client.count(alias).count, POINTS))
        check("a query through the alias returns results",
              lambda: _expect(
                  len(client.query_points(alias, query=[1.0] * DIM, limit=5).points) > 0, True))

        print("\nSwap without downtime\n")
        check("build v2 alongside the serving v1", lambda: build(v2, 25))
        check("v1 is untouched while v2 builds",
              lambda: _expect(client.count(v1).count, POINTS))
        check("switch the alias to v2", lambda: publish(v2))
        check("the alias now reads v2", lambda: _expect(client.count(alias).count, 25))

        print("\nRoll back\n")
        check("point the alias back at v1", lambda: publish(v1))
        check("the alias reads v1 again", lambda: _expect(client.count(alias).count, POINTS))
        check("v2 still exists, so rolling forward is another switch",
              lambda: _expect(client.collection_exists(v2), True))

    finally:
        print("\nCleanup\n")
        if alias_made:
            try:
                client.update_collection_aliases(change_aliases_operations=[
                    DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias))])
                print(f"  removed alias {alias}")
            except Exception as exc:  # noqa: BLE001
                print(f"  WARNING could not remove alias {alias}: {exc}")
        for name in created:
            try:
                client.delete_collection(name)
                print(f"  removed collection {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  WARNING could not remove {name}: {exc}")
        client.close()

    print()
    if failures:
        print(f"FAILED: {failures} check(s). Do not publish a corpus to this cluster yet.")
        return 1
    print("OK — versioned build, alias publish, atomic swap and rollback all work "
          "against the real cluster.")
    return 0


def _expect(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")
    return actual


if __name__ == "__main__":
    raise SystemExit(main())
