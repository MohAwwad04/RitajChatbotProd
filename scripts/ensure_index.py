"""Idempotent index bootstrap — for local development and CI, not for boot.

This script used to run from `scripts/start.sh` ahead of uvicorn, which is how a
slow embed took the whole deployment down (see that file's header). The web
service now initializes on a background thread via `ritaj.bootstrap`, and the
same logic lives there.

What remains useful here is running that bootstrap deliberately: to populate a
fresh developer machine, or to verify in CI that the published corpus artifact
restores and answers.

Usage:
    python scripts/ensure_index.py            # restore, or build if permitted
    python scripts/ensure_index.py --build    # force the in-process build path
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj import bootstrap, corpus  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true",
                    help="permit the in-process index build (slow path)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    version = corpus.current_version()
    print(f"Corpus artifact: {version or '(none published)'}")
    detail = bootstrap.initialize(allow_build=True if args.build else None)
    print(f"Ready. {detail.get('chunks')} chunks indexed.")
    for key in ("restore", "built", "warmup_retrieval_seconds"):
        if key in detail:
            print(f"  {key}: {detail[key]}")


if __name__ == "__main__":
    main()
