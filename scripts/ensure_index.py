"""Idempotent index bootstrap, run on web-service startup.

Builds the Qdrant collection from data/raw/ only if it's missing or empty, so
the first deploy populates the store and later restarts are no-ops. Embedding
the tiny corpus is fast once the e5 model is cached on the volume.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj import vectorstore  # noqa: E402
from ritaj.config import settings  # noqa: E402
from ritaj.ingest import build_index  # noqa: E402


def main() -> None:
    try:
        if vectorstore._client.collection_exists(settings.collection) and vectorstore.count() > 0:
            print(f"Index '{settings.collection}' already populated; skipping build.")
            return
    except Exception as exc:  # collection missing or store not reachable yet
        print(f"Index check failed ({exc}); building fresh.")
    print("Building index from data/raw/ ...")
    count = build_index()
    print(f"Done. {count} chunks indexed.")


if __name__ == "__main__":
    main()
