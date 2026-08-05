#!/usr/bin/env python3
"""Regenerate requirements.lock.txt — the exact, hashed runtime dependency set.

The container installs from this file with `pip install --require-hashes`, so
it is the definition of what ships. Two properties matter:

  * **Reproducible.** The previous Dockerfile ran `pip install -e .` with no
    pins, so two builds of the same commit could install different versions —
    which means the image that passed staging is not necessarily the image
    promoted to production.
  * **Tamper-evident.** Every artifact carries a hash, so a compromised mirror
    or a hijacked package name fails the install instead of running.

Runtime only: `--no-dev` keeps pytest and friends out of the production image.

Usage:
    python scripts/lock_deps.py            # regenerate the file
    python scripts/lock_deps.py --check    # fail if it is stale (CI gate)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock.txt"

EXPORT = [
    "uv", "export",
    "--no-dev",             # runtime only — pytest must not reach the image
    "--no-emit-project",    # the project itself is installed with `pip install -e .`
    "--format", "requirements.txt",
]

HEADER = """\
# GENERATED — do not edit. Regenerate with: python scripts/lock_deps.py
#
# The exact runtime dependency set, with a hash for every artifact. The
# container installs from this file with --require-hashes, so it is what ships.
#
# torch resolves to the Linux CPU wheel (torch==...+cpu) because pyproject.toml
# points it at PyTorch's CPU index for sys_platform == 'linux'. That keeps the
# ~2 GB nvidia-* CUDA stack out of a CPU-only image; the Dockerfile passes the
# matching --extra-index-url so those wheels can be found.
"""


def generate() -> str:
    try:
        result = subprocess.run(EXPORT, cwd=ROOT, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("uv is not installed — see https://docs.astral.sh/uv/")
    except subprocess.CalledProcessError as exc:
        sys.exit(f"uv export failed:\n{exc.stderr}")
    return HEADER + result.stdout


def summarize(text: str) -> str:
    packages = re.findall(r"(?m)^([A-Za-z0-9_.-]+)==", text)
    cuda = [p for p in packages if p.startswith(("nvidia", "triton"))]
    lines = [f"{len(packages)} package(s), {text.count('--hash=')} hash(es)"]
    if cuda:
        lines.append(f"  WARNING: CUDA packages present in a CPU-only image: {cuda}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed lock differs from a fresh export")
    args = ap.parse_args()

    fresh = generate()
    print(summarize(fresh))

    if args.check:
        current = LOCK.read_text(encoding="utf-8") if LOCK.exists() else ""
        if current != fresh:
            sys.exit(
                "requirements.lock.txt is stale — pyproject.toml or uv.lock changed "
                "without regenerating it. Run: python scripts/lock_deps.py"
            )
        print("lock is up to date with uv.lock")
        return

    LOCK.write_text(fresh, encoding="utf-8")
    print(f"Wrote {LOCK.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
