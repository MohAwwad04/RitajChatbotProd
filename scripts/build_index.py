"""Build the vector index from data/raw/.

Usage:  python scripts/build_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ritaj.ingest import build_index  # noqa: E402

if __name__ == "__main__":
    print("Building index from data/raw/ ...")
    count = build_index()
    print(f"Done. {count} chunks indexed.")
