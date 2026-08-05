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
    """Packages from requirements.lock.txt — the set the image actually installs.

    Read from the hashed lock rather than uv.lock, because uv.lock is the
    resolution *universe* (every platform, dev extras included) while the lock
    file is what `pip install --require-hashes` puts in the container. An SBOM
    listing packages that do not ship is worse than none: it sends a reviewer
    chasing CVEs in software that is not there, and hides the ones that are.

    Each entry carries its artifact hashes, so the SBOM can be checked against
    the image rather than trusted.
    """
    lock = ROOT / "requirements.lock.txt"
    if not lock.is_file():
        return []

    components: list[dict] = []
    current: dict | None = None
    for raw in lock.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)(.*)$", line)
        if match:
            name, version, rest = match.groups()
            marker = rest.split(";", 1)[1].strip().rstrip("\\").strip() if ";" in rest else ""
            current = {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
                "hashes": [],
            }
            if marker:
                # e.g. "sys_platform == 'linux'" — torch ships a different wheel
                # per platform, and the SBOM should say which.
                current["scope"] = marker
            components.append(current)
            continue
        hash_match = re.match(r"^--hash=sha256:([0-9a-f]{64})", line)
        if hash_match and current is not None:
            current["hashes"].append({"alg": "SHA-256", "content": hash_match.group(1)})
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
        entry = {
            "type": "library",
            # These are BUILD-time only: what ships is the bundled output in
            # ritaj-student-portal/dist, not node_modules. They are listed
            # because a compromised build dependency can poison that output,
            # but they are not judged by the runtime pinning check.
            "scope": "build",
            "name": name,
            "version": meta["version"],
            "purl": f"pkg:npm/{name}@{meta['version']}",
            "hashes": [],
        }
        integrity = meta.get("integrity", "")
        if integrity.startswith("sha512-"):
            entry["hashes"].append({"alg": "SHA-512", "content": integrity[len("sha512-"):]})
        elif integrity.startswith("sha1-"):
            entry["hashes"].append({"alg": "SHA-1", "content": integrity[len("sha1-"):]})
        components.append(entry)
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
    libraries = 0
    unhashed: list[str] = []

    for component in sbom["components"]:
        kind = component["type"]
        if kind == "container" and not component.get("pinned_by_digest"):
            print(f"  WARN  base image {component['name']}:{component['version']} is "
                  "pinned by tag, not digest — a rebuild can pull a different image")
            problems += 1
        if kind == "machine-learning-model" and "unpinned" in component["version"]:
            print(f"  WARN  model {component['name']} has no pinned revision — a "
                  "rebuild can bake different weights")
            problems += 1
        # Only runtime artifacts are judged here. Build-time npm packages are
        # listed for supply-chain review but never enter the container.
        if kind == "library" and component.get("scope") != "build":
            libraries += 1
            if not component.get("hashes"):
                unhashed.append(component["name"])

    if not libraries:
        print("  WARN  no runtime dependencies found — run scripts/lock_deps.py")
        problems += 1
    if unhashed:
        print(f"  WARN  {len(unhashed)} dependency/dependencies have no artifact hash: "
              f"{', '.join(unhashed[:5])}")
        problems += 1

    # A CPU-only image that ships the CUDA stack is both 2 GB larger and a
    # larger attack surface for no benefit.
    cuda = [c["name"] for c in sbom["components"]
            if c["name"].startswith(("nvidia", "triton"))]
    if cuda:
        print(f"  WARN  CUDA packages in a CPU-only image: {', '.join(cuda[:5])}")
        problems += 1

    if not problems:
        print(f"  all deployable components are pinned "
              f"({libraries} hashed dependencies, digest-pinned base image)")
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
