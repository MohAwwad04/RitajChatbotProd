#!/usr/bin/env python3
"""Emit the release manifest — what exactly is (or would be) deployed.

Roadmap Phase 0, task 3. A deployment is only reproducible if you can name the
four things that determine its behaviour:

  1. the commit the image was built from (and whether the tree was clean),
  2. the corpus artifact version the answers come from,
  3. the LLM provider + model that generates them,
  4. the extension version students are running against it.

Rollback means "redeploy the previous manifest", so this file is written next to
the artifact and kept for at least the last two releases.

Usage:
    python scripts/release_manifest.py                 # print to stdout
    python scripts/release_manifest.py -o release/manifest.json
    python scripts/release_manifest.py --deployed       # stamp deployed_at=now
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _git(*args: str) -> str:
    """Run a git command in the repo; '' if git is unavailable or it fails."""
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def is_clean() -> bool:
    """True when the working tree has no tracked modifications or new files."""
    return _git("status", "--porcelain") == ""


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _base_image() -> str | None:
    """The Dockerfile's FROM reference, so the manifest names the exact base."""
    try:
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    except OSError:
        return None
    import re  # noqa: PLC0415

    match = re.search(r"^FROM\s+(\S+)", text, re.M)
    return match.group(1) if match else None


def _provider(base_url: str) -> str:
    """Name the LLM host from its base URL — for the manifest and privacy copy.

    The provider name is a *disclosure*, not decoration: Phase 8 requires the
    privacy policy to name the actual model host, so it must be derived from the
    configured endpoint rather than hand-maintained.
    """
    host = (urlparse(base_url).hostname or "").lower()
    known = {
        "api.cloudflare.com": "cloudflare-workers-ai",
        "api.groq.com": "groq",
        "api.openai.com": "openai",
        "localhost": "local",
        "127.0.0.1": "local",
    }
    return known.get(host, host or "unset")


def build(deployed: bool = False) -> dict:
    from ritaj import __version__ as app_version  # noqa: PLC0415
    from ritaj.config import settings  # noqa: PLC0415
    from ritaj.corpus import current_version  # noqa: PLC0415

    manifest_path = ROOT / "chrome-extension" / "manifest.json"
    try:
        ext = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ext = {}

    zip_path = ROOT / "ritaj-assistant-extension.zip"

    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deployed_at": (
            datetime.now(timezone.utc).isoformat(timespec="seconds") if deployed else None
        ),
        "app": {
            "version": app_version,
            # Model identity is (repo, revision). The repo name alone resolves to
            # whatever is on the hub that day, so a rebuild could bake different
            # weights than the release evaluation was run against — and the
            # manifest would not show it.
            "embed_model": settings.embed_model,
            "embed_revision": settings.embed_revision,
            "rerank_model": settings.rerank_model,
            "rerank_revision": settings.rerank_revision,
        },
        "dependencies": {
            # The hashed runtime lock the container installs from. Its digest
            # pins the whole dependency set in one value a reviewer can compare.
            "lock_sha256": _sha256(ROOT / "requirements.lock.txt"),
            "base_image": _base_image(),
        },
        "commit": {
            "sha": _git("rev-parse", "HEAD"),
            "short": _git("rev-parse", "--short", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "tag": _git("tag", "--points-at", "HEAD"),
            "clean": is_clean(),
        },
        "corpus": {
            # None until Phase 2's build_index.py has published an artifact.
            "version": current_version(),
        },
        "llm": {
            "provider": _provider(settings.llm_base_url),
            "model": settings.llm_model,
            # Host only — the full URL embeds the Cloudflare account id.
            "endpoint_host": urlparse(settings.llm_base_url).hostname or "",
        },
        "extension": {
            "version": ext.get("version"),
            "permissions": ext.get("permissions", []),
            "host_permissions": ext.get("host_permissions", []),
            "zip_sha256": _sha256(zip_path),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", type=Path, help="write JSON here instead of stdout")
    ap.add_argument("--deployed", action="store_true", help="stamp deployed_at with now")
    ap.add_argument(
        "--require-clean",
        action="store_true",
        help="exit non-zero if the working tree is dirty (release gate)",
    )
    args = ap.parse_args()

    manifest = build(deployed=args.deployed)
    if args.require_clean and not manifest["commit"]["clean"]:
        sys.exit("Working tree is dirty — a release manifest must describe a committed tree.")

    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
