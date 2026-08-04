#!/usr/bin/env python3
"""One-command deploy of a reviewed commit to a Hugging Face Space.

Usage:
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py                 # production
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py --space staging # staging
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py --allow-dirty --space staging

Stages exactly what the Dockerfile needs (plus the Space README front-matter),
uploads it to the Space repo (which triggers a rebuild), and — if ADMIN_TOKEN
is given — sets/updates that Space secret first. Requires an HF token with
Write access to the Space (https://huggingface.co/settings/tokens).

Release control (roadmap Phase 0, task 4): this script used to upload whatever
happened to be in the working directory. A production deploy now REFUSES a dirty
tree, so what runs in front of students always corresponds to a commit someone
can review and roll back to. `--allow-dirty` exists for iterating on a non-
production preview Space and is rejected for the production Space.

The staged tree also carries `release/manifest.json` (commit SHA, corpus
version, provider/model, extension version) so the deployed artifact can say
what it is — see scripts/release_manifest.py.

See DEPLOYMENT.md for the full context and IDs.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SPACE_ID = "MohAwwad04/ritaj-rag"
# Staging gets its own Space so a broken build never takes production down. The
# id is overridable because the account that owns it may differ per operator.
STAGING_SPACE_ID = os.environ.get("STAGING_SPACE_ID", "MohAwwad04/ritaj-rag-staging")
ROOT = Path(__file__).resolve().parents[1]

# The YAML front-matter HF Spaces requires at the top of the repo README.
SPACE_README = """---
title: Ritaj RAG
emoji: 🎓
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# Ritaj Assistant — Birzeit University RAG chatbot

Grounded, cited answers about Birzeit University and the Ritaj portal.
Backend + student portal + operator console in one container.
"""

# Everything the Dockerfile COPYs, plus the Dockerfile itself.
STAGE_ITEMS = ["Dockerfile", "pyproject.toml", "src", "data", "scripts",
               "ritaj-student-portal/dist"]

# Never stage these, whatever ends up inside a staged directory: the quarantine
# folder holds corpus material that deliberately failed source policy (Phase 2),
# and the raw snapshots are audit inputs, not runtime data.
STAGE_EXCLUDE = shutil.ignore_patterns(
    "__pycache__", ".DS_Store", "*.pyc", "quarantine", "snapshots", ".env", "*.rtf",
)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _require_clean_tree(target_space: str, allow_dirty: bool) -> None:
    """Refuse to deploy an unreviewable tree.

    A dirty tree cannot be rolled back to (there is no commit to name), and it
    can carry local experiments nobody reviewed. `--allow-dirty` is a deliberate
    development affordance for a preview Space only — it is refused for
    production, where the whole point of this gate is that it cannot be waived.
    """
    dirty = _git("status", "--porcelain")
    if not dirty:
        return
    if target_space == SPACE_ID:
        sys.exit(
            "Refusing to deploy a dirty working tree to PRODUCTION "
            f"({SPACE_ID}).\n\n{dirty}\n\n"
            "Commit (and preferably tag) the release first, or deploy to the "
            "staging Space with --space staging --allow-dirty."
        )
    if not allow_dirty:
        sys.exit(
            f"Working tree is dirty:\n\n{dirty}\n\n"
            "Pass --allow-dirty to deploy it to the non-production Space anyway."
        )
    print("WARNING: deploying a DIRTY tree to a preview Space — not reproducible.")


def _write_manifest(stage: Path, allow_dirty: bool) -> dict:
    """Build the release manifest into the staged tree (best-effort)."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from release_manifest import build  # noqa: PLC0415
    except ImportError:
        sys.path.insert(0, str(ROOT / "scripts"))
        from release_manifest import build  # noqa: PLC0415
    manifest = build(deployed=True)
    out = stage / "release" / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("message", nargs="?", default=None,
                    help="commit message for the Space upload")
    ap.add_argument("--space", default="production", choices=["production", "staging"],
                    help="which Space to deploy to (default: production)")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="allow an uncommitted tree (non-production Spaces only)")
    args = ap.parse_args()

    space_id = SPACE_ID if args.space == "production" else STAGING_SPACE_ID
    _require_clean_tree(space_id, args.allow_dirty)

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (a Write token from huggingface.co/settings/tokens).")

    from huggingface_hub import add_space_secret, upload_folder

    admin_token = os.environ.get("ADMIN_TOKEN")
    if admin_token:
        add_space_secret(space_id, "ADMIN_TOKEN", admin_token, token=token)
        print(f"ADMIN_TOKEN secret set on {space_id}.")

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        (stage / "README.md").write_text(SPACE_README, encoding="utf-8")
        for item in STAGE_ITEMS:
            src, dst = ROOT / item, stage / item
            if not src.exists():
                sys.exit(f"Missing {item} — build the portal first (npm run build).")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=STAGE_EXCLUDE)
            else:
                shutil.copy2(src, dst)

        manifest = _write_manifest(stage, args.allow_dirty)
        commit = manifest["commit"]
        print(f"Release: commit {commit['short'] or '?'} ({commit['branch'] or '?'}), "
              f"corpus {manifest['corpus']['version'] or 'UNBUILT'}, "
              f"llm {manifest['llm']['provider']}/{manifest['llm']['model']}")

        message = args.message or f"deploy: {commit['short'] or 'working tree'}"
        print(f"Uploading to {space_id} (triggers a rebuild)…")
        upload_folder(repo_id=space_id, repo_type="space", folder_path=str(stage),
                      token=token, commit_message=message)
    print("Done. Watch the build at https://huggingface.co/spaces/" + space_id)


if __name__ == "__main__":
    main()
