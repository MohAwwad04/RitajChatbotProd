#!/usr/bin/env python3
"""Build the Chrome Web Store package — deterministically, from a clean tree.

The documented procedure was a `zip -r` one-liner in a markdown file. Three
problems with that: it zips whatever is in the working tree (including
uncommitted experiments), it produces a different archive every run because zip
records mtimes, and the exclusion list lived only in prose so it drifted.

This produces a **byte-identical archive for a given commit**: entries sorted,
timestamps fixed, permissions normalised. That is what makes the checksum in
`release/manifest.json` mean anything — two people building the same tag can
compare hashes instead of trusting each other.

Usage:
    python scripts/package_extension.py             # refuses a dirty tree
    python scripts/package_extension.py --allow-dirty   # local testing only
    python scripts/package_extension.py --verify    # rebuild and compare hashes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "chrome-extension"
OUTPUT = ROOT / "ritaj-assistant-extension.zip"

# Everything the extension needs at runtime, and nothing else. An allowlist,
# not an ignore list: a new test file or a store draft added later is excluded
# by default rather than shipping because nobody updated an exclusion pattern.
INCLUDE_FILES = [
    "manifest.json",
    "config.js",
    "navigation.js",
    "service-worker.js",
    "sidepanel.html",
    "sidepanel.css",
    "sidepanel.js",
]
INCLUDE_GLOBS = ["icons/*.png"]

# A fixed timestamp so the archive is reproducible. 1980-01-01 is the earliest
# value the zip format can represent.
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def tree_is_dirty() -> str:
    try:
        return subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def collect() -> list[Path]:
    files: list[Path] = []
    for name in INCLUDE_FILES:
        path = EXT / name
        if not path.is_file():
            sys.exit(f"missing required extension file: {name}")
        files.append(path)
    for pattern in INCLUDE_GLOBS:
        matched = sorted(EXT.glob(pattern))
        if not matched:
            sys.exit(f"no files matched required pattern: {pattern}")
        files.extend(matched)
    return sorted(files, key=lambda p: p.relative_to(EXT).as_posix())


def build(destination: Path) -> str:
    files = collect()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(EXT).as_posix(), date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # normalise permissions
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allow-dirty", action="store_true",
                    help="package an uncommitted tree (local testing only)")
    ap.add_argument("--verify", action="store_true",
                    help="build twice and confirm the archives are identical")
    ap.add_argument("-o", "--output", type=Path, default=OUTPUT)
    args = ap.parse_args()

    dirty = tree_is_dirty()
    if dirty and not args.allow_dirty:
        sys.exit(
            "Refusing to package a dirty working tree — the archive would not "
            f"correspond to any commit.\n\n{dirty}\n\n"
            "Commit and tag the release, or pass --allow-dirty for local testing."
        )
    if dirty:
        print("WARNING: packaging a DIRTY tree — not reproducible, do not submit.")

    version = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))["version"]
    digest = build(args.output)

    if args.verify:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            second = build(Path(tmp) / "again.zip")
        if second != digest:
            sys.exit(f"NOT reproducible: {digest} != {second}")
        print("reproducible: two builds produced identical archives")

    size_kb = args.output.stat().st_size / 1024
    print(f"Built {args.output.name}  v{version}  {size_kb:.1f} KB")
    print(f"sha256  {digest}")
    print("\nRecord this checksum in release/manifest.json:")
    print("  python scripts/release_manifest.py -o release/manifest.json")


if __name__ == "__main__":
    main()
