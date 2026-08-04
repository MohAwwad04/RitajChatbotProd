#!/usr/bin/env python3
"""One-command deploy of the current working tree to the Hugging Face Space.

Usage:
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py
    HF_TOKEN=hf_xxx ADMIN_TOKEN=yyy .venv/bin/python scripts/deploy_space.py

Stages exactly what the Dockerfile needs (plus the Space README front-matter),
uploads it to the Space repo (which triggers a rebuild), and — if ADMIN_TOKEN
is given — sets/updates that Space secret first. Requires an HF token with
Write access to the Space (https://huggingface.co/settings/tokens).

See DEPLOYMENT.md for the full context and IDs.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

SPACE_ID = "MohAwwad04/ritaj-rag"
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


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (a Write token from huggingface.co/settings/tokens).")

    from huggingface_hub import add_space_secret, upload_folder

    admin_token = os.environ.get("ADMIN_TOKEN")
    if admin_token:
        add_space_secret(SPACE_ID, "ADMIN_TOKEN", admin_token, token=token)
        print("ADMIN_TOKEN secret set on the Space.")

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
                shutil.copytree(src, dst,
                                ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
            else:
                shutil.copy2(src, dst)

        message = sys.argv[1] if len(sys.argv) > 1 else "deploy: sync working tree"
        print(f"Uploading to {SPACE_ID} (triggers a rebuild)…")
        upload_folder(repo_id=SPACE_ID, repo_type="space", folder_path=str(stage),
                      token=token, commit_message=message)
    print("Done. Watch the build at https://huggingface.co/spaces/" + SPACE_ID)


if __name__ == "__main__":
    main()
