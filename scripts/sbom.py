#!/usr/bin/env python3
"""Produce a software bill of materials for the release artifact.

Roadmap Phase 8, task 10. Three trees ship together and each can carry a
vulnerability the others don't: the Python backend, the portal's npm tree, and
the container base image. A release needs one document naming all three at the
versions that actually shipped.

CycloneDX-shaped JSON, because that is what dependency scanners consume — but
generated from the lockfiles present in this repo rather than by installing a
scanner, so it runs anywhere the tests run.

Usage:
    python scripts/sbom.py                  # write release/sbom.json
    python scripts/sbom.py --print          # to stdout
    python scripts/sbom.py --check-pinned   # fail if a deployable isn't pinned
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_components() -> list[dict]:
    """Packages from uv.lock (exact, resolved versions)."""
    lock = ROOT / "uv.lock"
    if not lock.is_file():
        return []
    text = lock.read_text(encoding="utf-8")
    components = []
    # uv.lock is TOML with [[package]] blocks; parsing the two fields we need
    # avoids a tomllib version dance and a dependency on the exact schema.
    for block in re.finditer(
        r'\[\[package\]\]\s*\nname = "([^"]+)"\s*\nversion = "([^"]+)"', text
    ):
        components.append({
            "type": "library",
            "name": block.group(1),
            "version": block.group(2),
            "purl": f"pkg:pypi/{block.group(1)}@{block.group(2)}",
        })
    return components


def npm_components() -> list[dict]:
    """Packages from the portal's package-lock.json."""
    lock = ROOT / "ritaj-student-portal" / "package-lock.json"
    if not lock.is_file():
        return []
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except ValueError:
        return []
    components = []
    for path, meta in (data.get("packages") or {}).items():
        if not path or not meta.get("version"):
            continue
        name = meta.get("name") or path.split("node_modules/")[-1]
        components.append({
            "type": "library",
            "name": name,
            "version": meta["version"],
            "purl": f"pkg:npm/{name}@{meta['version']}",
            "scope": "optional" if meta.get("dev") else "required",
        })
    return components


def base_image() -> dict | None:
    """The Dockerfile's FROM line — pinned or not."""
    dockerfile = ROOT / "Dockerfile"
    if not dockerfile.is_file():
        return None
    match = re.search(r"^FROM\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.M)
    if not match:
        return None
    reference = match.group(1)
    return {
        "type": "container",
        "name": reference.split(":")[0],
        "version": reference.split(":", 1)[1] if ":" in reference else "latest",
        "purl": f"pkg:docker/{reference}",
        "pinned_by_digest": "@sha256:" in reference,
    }


def models() -> list[dict]:
    """The ML models baked into the image — part of what ships, and versioned
    only by a moving Hugging Face tag unless a revision is pinned."""
    from ritaj.config import settings

    return [
        {"type": "machine-learning-model", "name": settings.embed_model,
         "version": settings.embed_revision or "unpinned"},
        {"type": "machine-learning-model", "name": settings.rerank_model,
         "version": settings.rerank_revision or "unpinned"},
    ]


def build() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    components = python_components() + npm_components() + models()
    image = base_image()
    if image:
        components.append(image)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "component": {"type": "application", "name": "ritaj-assistant"},
            "tools": [{"name": "scripts/sbom.py"}],
        },
        "components": components,
    }


def check_pinned(sbom: dict) -> int:
    """Deployable artifacts must be reproducible. Returns the problem count."""
    problems = 0
    for component in sbom["components"]:
        if component["type"] == "container" and not component.get("pinned_by_digest"):
            print(f"  WARN  base image {component['name']}:{component['version']} is "
                  "pinned by tag, not digest — a rebuild can pull a different image")
            problems += 1
        if component["type"] == "machine-learning-model" and "unpinned" in component["version"]:
            print(f"  WARN  model {component['name']} has no pinned revision — a "
                  "rebuild can bake different weights")
            problems += 1
    if not problems:
        print("  all deployable components are pinned")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", dest="to_stdout")
    ap.add_argument("--check-pinned", action="store_true")
    args = ap.parse_args()

    sbom = build()
    counts: dict[str, int] = {}
    for component in sbom["components"]:
        counts[component["type"]] = counts.get(component["type"], 0) + 1

    if args.check_pinned:
        print("Pinning check\n")
        problems = check_pinned(sbom)
        print(f"\n{len(sbom['components'])} component(s): "
              + ", ".join(f"{n} {t}" for t, n in sorted(counts.items())))
        sys.exit(1 if problems else 0)

    text = json.dumps(sbom, indent=2)
    if args.to_stdout:
        print(text)
        return
    out = ROOT / "release" / "sbom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} — "
          + ", ".join(f"{n} {t}" for t, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
