#!/usr/bin/env python3
"""One-command deploy of a reviewed commit to a Hugging Face Space.

Usage:
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py                 # production
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py --space staging # staging
    HF_TOKEN=hf_xxx .venv/bin/python scripts/deploy_space.py --allow-dirty --space staging

Stages exactly what the Dockerfile needs (plus the Space README front-matter),
uploads it to the Space repo (which triggers a rebuild), and first pushes every
secret and variable present in this shell's environment (SPACE_SECRETS /
SPACE_VARIABLES below). Requires an HF token with Write access to the Space
(https://huggingface.co/settings/tokens).

A production deploy is refused up front when a fail-closed setting is missing.
The container validates the same things at boot, but by then it has spent ~20
minutes building and dies in its health check — which is precisely the state the
existing Space has been sitting in ("Launch timed out, workload was not healthy
after 30 min"). Checking here turns a 20-minute failure into an instant one.

See SETUP_LIVE.md for the accounts and values this needs.

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
STAGE_ITEMS = ["Dockerfile", "requirements.lock.txt", "pyproject.toml", "src",
               "data", "scripts", "ritaj-student-portal/dist"]


def _dockerfile_sources() -> list[str]:
    """Every path the Dockerfile COPYs in, read from the Dockerfile itself.

    STAGE_ITEMS is a hand-written restatement of what the image needs, and it
    drifted: `requirements.lock.txt` was added to the Dockerfile and never to
    this list, so every deploy uploaded a tree that could not build. The failure
    surfaced twenty minutes later as BUILD_ERROR, "failed to calculate checksum
    of ref ... /requirements.lock.txt: not found".

    Deriving the requirement from the artifact instead of restating it means the
    next COPY added to the Dockerfile fails here, before the upload, rather than
    in the build queue.
    """
    sources: list[str] = []
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        parts = stripped.split()[1:]
        # Drop flags like --from=builder, then the final token (the destination).
        parts = [t for t in parts if not t.startswith("--")]
        sources.extend(parts[:-1])
    return sources


def _check_stage_covers_dockerfile() -> None:
    """Fail before uploading if the image would be missing a file it COPYs."""
    missing = []
    for source in _dockerfile_sources():
        covered = any(
            source == item or source.startswith(item.rstrip("/") + "/")
            for item in STAGE_ITEMS
        )
        if not covered:
            missing.append(source)
    if missing:
        sys.exit(
            "Dockerfile COPYs paths that deploy_space.py does not stage:\n  "
            + "\n  ".join(missing)
            + "\n\nAdd them to STAGE_ITEMS. The build would otherwise fail ~20 "
              "minutes from now with 'failed to calculate checksum of ref'."
        )

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


# Runtime configuration pushed to the Space, split by sensitivity.
#
# SECRETS are write-only once set: HF does not show them again in the settings
# page, and they are not copied into a duplicated Space. VARIABLES are public
# and visible, which is correct for everything that is a deployment choice
# rather than a credential.
#
# Both are read from this machine's environment, never from a file in the repo,
# so a key cannot reach a commit by being staged with everything else.
SPACE_SECRETS = [
    "LLM_API_KEY",       # Cloudflare Workers AI inference token
    # A secret, not a variable, because the Cloudflare account id is embedded in
    # its path and Space VARIABLES are publicly viewable on the settings page.
    # scripts/secret_inventory.py already classified CF_ACCOUNT_ID this way
    # ("identifies the billing account"); putting the URL in the public list
    # would have published it on every deploy.
    "LLM_BASE_URL",
    "QDRANT_API_KEY",    # only when QDRANT_MODE=remote
    "ADMIN_USERS",       # username:bcrypt_hash pairs — never plaintext
    "ADMIN_TOKEN",       # legacy single token; ADMIN_USERS supersedes it
    "SESSION_SECRET",    # signs admin session tokens
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
]

SPACE_VARIABLES = [
    "ENVIRONMENT", "STARTUP_INIT", "ALLOW_INDEX_BUILD_ON_BOOT",
    "LLM_MODEL", "LLM_DAILY_NEURON_BUDGET",
    "MAX_CONCURRENT_GENERATIONS", "TRUSTED_PROXY_COUNT",
    "QDRANT_MODE", "QDRANT_URL", "QDRANT_COLLECTION_ALIAS", "QDRANT_PATH",
    "COLLECTION", "CHAT_LOG_MODE", "CHAT_LOG_RETENTION_DAYS",
    "CORS_ORIGINS", "EXTENSION_ID",
    "MAX_MESSAGE_CHARS", "MAX_BODY_BYTES", "HISTORY_MAX_TURNS", "HISTORY_MAX_CHARS",
]

# What production genuinely cannot start without. Checked HERE, before the
# upload, because the alternative is discovering it from a Space that builds for
# twenty minutes and then dies in config.check_production_config() — which is
# exactly the "Launch timed out" the existing Space has been sitting in.
PRODUCTION_REQUIRED = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "CORS_ORIGINS"]


def _push_configuration(space_id: str, token: str, *, production: bool) -> None:
    """Set every provided secret and variable on the Space before uploading."""
    from huggingface_hub import (  # noqa: PLC0415
        add_space_secret,
        add_space_variable,
        delete_space_secret,
        delete_space_variable,
    )

    if production:
        missing = [k for k in PRODUCTION_REQUIRED if not os.environ.get(k)]
        # ADMIN_USERS or ADMIN_TOKEN — either satisfies the auth requirement.
        if not (os.environ.get("ADMIN_USERS") or os.environ.get("ADMIN_TOKEN")):
            missing.append("ADMIN_USERS (or ADMIN_TOKEN)")
        if missing:
            sys.exit(
                "Refusing to deploy to production without:\n  "
                + "\n  ".join(missing)
                + "\n\nThe container is fail-closed on these "
                  "(config.check_production_config), so it would build for ~20 "
                  "minutes and then fail its health check. Set them in this "
                  "shell and re-run. See SETUP_LIVE.md."
            )

    # Hugging Face refuses to start a Space where one name exists as BOTH a
    # variable and a secret ("Collision on variables and secrets names"), and it
    # reports that only as CONFIG_ERROR after the upload. This Space was first
    # configured for a different provider in July, so several names were left in
    # the opposite namespace to the one they belong in now — LLM_BASE_URL in
    # particular moved to secrets once it started carrying the account id.
    #
    # So each name is cleared from the namespace it must NOT be in, immediately
    # before being written to the one it must. Deliberately narrow: a name is
    # only ever removed from the wrong side, never from the side it is about to
    # be written to, so nothing whose value we do not hold is destroyed.
    def _clear_opposite(name: str, *, wanted: str) -> None:
        remove = delete_space_variable if wanted == "secret" else delete_space_secret
        try:
            remove(space_id, name, token=token)
            print(f"  cleared stale {'variable' if wanted == 'secret' else 'secret'} {name}")
        except Exception:  # noqa: BLE001 — absent is the normal case, and fine
            pass

    set_secrets, set_variables = [], []
    for name in SPACE_SECRETS:
        value = os.environ.get(name)
        if value:
            _clear_opposite(name, wanted="secret")
            add_space_secret(space_id, name, value, token=token)
            set_secrets.append(name)
    for name in SPACE_VARIABLES:
        value = os.environ.get(name)
        if value:
            _clear_opposite(name, wanted="variable")
            add_space_variable(space_id, name, value, token=token)
            set_variables.append(name)

    if set_secrets:
        # Names only. The values are the thing being protected.
        print(f"Secrets set on {space_id}: {', '.join(set_secrets)}")
    if set_variables:
        print(f"Variables set on {space_id}: {', '.join(set_variables)}")
    if not set_secrets and not set_variables:
        print("No configuration supplied in the environment — leaving the Space's as-is.")


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
    _check_stage_covers_dockerfile()
    _require_clean_tree(space_id, args.allow_dirty)

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (a Write token from huggingface.co/settings/tokens).")

    from huggingface_hub import add_space_secret, add_space_variable, upload_folder

    _push_configuration(space_id, token, production=args.space == "production")

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
