#!/usr/bin/env python3
"""CI gate: the extension asks for no more than it needs, and its allowlist matches.

Chrome Web Store policy requires minimal permissions and accurate disclosure.
Three failures this catches, all of which would ship an extension whose
behaviour contradicts its listing:

  1. **A prohibited permission.** `tabs`, `scripting`, `webRequest`,
     `<all_urls>` or Ritaj host access would let the extension read the
     student's page. The privacy policy says it does not, so requesting one
     makes the policy false — and Chrome states that creating or navigating a
     tab does not need `tabs` in the first place.
  2. **Allowlist drift.** chrome-extension/navigation.js hardcodes the
     permitted paths on purpose: an independent check that read its allowlist
     from the response it is checking would not be independent. Duplication has
     to be verified, or it silently rots.
  3. **Leftover popup wiring.** A `default_popup` alongside a side panel means
     the icon still opens a popup and the panel is dead code.

Usage: python scripts/check_extension.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "chrome-extension"

# Permissions that would contradict the privacy disclosure, and why.
PROHIBITED = {
    "tabs": "reads tab URLs/titles; creating or navigating a tab does not need it",
    "scripting": "injects code into pages — the extension does not read pages",
    "activeTab": "grants page access on click; not needed for navigation-only",
    "webRequest": "observes network traffic",
    "webNavigation": "observes browsing activity",
    "cookies": "reads cookies — explicitly out of scope",
    "history": "reads browsing history",
    "bookmarks": "unrelated to the product",
    "downloads": "unrelated to the product",
    "management": "unrelated to the product",
    "debugger": "unrelated to the product",
    "<all_urls>": "blanket host access",
}

ALLOWED_PERMISSIONS = {"storage", "sidePanel"}


def check_manifest() -> int:
    errors = 0
    path = EXT / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    if manifest.get("manifest_version") != 3:
        print("  ERROR manifest_version must be 3")
        errors += 1

    action = manifest.get("action", {})
    if "default_popup" in action:
        print("  ERROR action.default_popup is set — the icon must open the side panel")
        errors += 1

    if not manifest.get("side_panel", {}).get("default_path"):
        print("  ERROR side_panel.default_path is missing")
        errors += 1
    else:
        panel = EXT / manifest["side_panel"]["default_path"]
        if not panel.is_file():
            print(f"  ERROR side_panel.default_path {panel.name} does not exist")
            errors += 1

    worker = manifest.get("background", {}).get("service_worker")
    if not worker:
        print("  ERROR background.service_worker is missing")
        errors += 1
    elif not (EXT / worker).is_file():
        print(f"  ERROR service worker {worker} does not exist")
        errors += 1

    permissions = set(manifest.get("permissions", []))
    for permission in sorted(permissions):
        if permission in PROHIBITED:
            print(f"  ERROR prohibited permission {permission!r}: {PROHIBITED[permission]}")
            errors += 1
        elif permission not in ALLOWED_PERMISSIONS:
            print(f"  ERROR undeclared permission {permission!r} — add it to "
                  "ALLOWED_PERMISSIONS here and to the store justification first")
            errors += 1

    for host in manifest.get("host_permissions", []):
        if host in PROHIBITED or host == "<all_urls>":
            print(f"  ERROR blanket host permission {host!r}")
            errors += 1
        if "ritaj.birzeit.edu" in host:
            print(f"  ERROR host permission on Ritaj ({host!r}) — the extension opens "
                  "Ritaj pages but must not be able to read them")
            errors += 1

    if not errors:
        print(f"  manifest OK — v{manifest['version']}, "
              f"permissions {sorted(permissions)}, "
              f"hosts {manifest.get('host_permissions', [])}")
    return errors


def check_allowlist_matches_registry() -> int:
    """navigation.js's hardcoded paths must cover exactly the registry's."""
    import yaml

    records = yaml.safe_load((ROOT / "data" / "navigation.yaml").read_text(encoding="utf-8")) or []
    registry_paths = set()
    for record in records:
        destination = record.get("destination", "")
        path = urlparse(destination).path or "/"
        if len(path) > 1:
            path = path.rstrip("/")
        registry_paths.add(path)

    source = (EXT / "navigation.js").read_text(encoding="utf-8")
    block = re.search(r"ALLOWED_PATHS\s*=\s*new Set\(\[(.*?)\]\)", source, re.S)
    if not block:
        print("  ERROR could not find ALLOWED_PATHS in navigation.js")
        return 1
    js_paths = set(re.findall(r"'([^']*)'", block.group(1)))

    errors = 0
    for missing in sorted(registry_paths - js_paths):
        print(f"  ERROR registry path {missing!r} is not in navigation.js ALLOWED_PATHS")
        errors += 1
    for extra in sorted(js_paths - registry_paths):
        print(f"  ERROR navigation.js allows {extra!r}, which no registry action uses")
        errors += 1
    if not errors:
        print(f"  allowlist OK — {len(js_paths)} path(s) match data/navigation.yaml")
    return errors


def check_request_limits_match() -> int:
    """The extension's declared message limit must equal the server's.

    Three sources once disagreed: MAX_MESSAGE_CHARS said 2000 and nothing read
    it, the request schema said 8000, and the extension had no limit at all. The
    panel refuses locally so a student gets a sentence instead of a 422 — which
    is only an improvement while the two numbers agree.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from ritaj.config import settings  # noqa: PLC0415

    source = (EXT / "config.js").read_text(encoding="utf-8")
    match = re.search(r"MAX_MESSAGE_CHARS\s*=\s*(\d+)", source)
    if not match:
        print("  ERROR chrome-extension/config.js does not declare MAX_MESSAGE_CHARS")
        return 1
    declared = int(match.group(1))
    if declared != settings.max_message_chars:
        print(f"  ERROR config.js MAX_MESSAGE_CHARS={declared} but the server's "
              f"max_message_chars={settings.max_message_chars}")
        return 1
    print(f"  request limits OK — both sides agree on {declared} characters")
    return 0


def check_no_stale_references() -> int:
    """No file still points at the removed popup, and no remote script is loaded."""
    errors = 0
    for path in sorted(EXT.rglob("*")):
        if path.suffix.lower() not in {".js", ".html", ".css", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        if re.search(r"\bpopup\.(js|css|html)\b", text):
            print(f"  ERROR {rel} still references the removed popup files")
            errors += 1
        # A strict CSP is the default for MV3, but an http(s) src in markup is
        # worth catching before a reviewer does.
        for match in re.finditer(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', text):
            print(f"  ERROR {rel} loads a remote resource: {match.group(1)}")
            errors += 1
    if not errors:
        print("  no stale popup references, no remote resources")
    return errors


def check_bundled_actions_current() -> int:
    """The offline registry the extension ships must match data/navigation.yaml.

    chrome-extension/actions.generated.js is what the page-finder falls back to
    when the backend is unreachable, so a stale copy would keep offering a
    destination after it was withdrawn — precisely defeating the server-side
    kill switch that exists so a bad URL can be pulled without a Store review.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "sync_extension_actions.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout + result.stderr).strip()
    for line in output.splitlines():
        print(f"  {line}")
    return 0 if result.returncode == 0 else 1


def check_source_link_hosts() -> int:
    """Every host data/links.yaml cites must be in the extension's link policy.

    chrome-extension/links.js validates citations against an exact host set. If
    the curated map gains a host the extension does not know, the panel silently
    drops that citation — the answer keeps its claim and loses its evidence,
    which is the worst of the available failures.
    """
    links_yaml = ROOT / "data" / "links.yaml"
    policy = EXT / "links.js"
    if not links_yaml.exists() or not policy.exists():
        print("  ERROR data/links.yaml or chrome-extension/links.js is missing")
        return 1

    block = re.search(r"OFFICIAL_HOSTS\s*=\s*new Set\(\[(.*?)\]\)", policy.read_text(
        encoding="utf-8"), re.S)
    if not block:
        print("  ERROR could not find OFFICIAL_HOSTS in links.js")
        return 1
    allowed = set(re.findall(r"'([^']+)'", block.group(1)))

    cited = set()
    for url in re.findall(r'url:\s*"([^"]+)"', links_yaml.read_text(encoding="utf-8")):
        host = (urlparse(url).hostname or "").lower()
        if host:
            cited.add(host)

    missing = sorted(cited - allowed)
    for host in missing:
        print(f"  ERROR data/links.yaml cites {host!r}, which links.js will reject")
    if missing:
        return len(missing)

    unused = sorted(allowed - cited)
    for host in unused:
        # Not an error: a host may be allowed ahead of the map gaining an entry.
        # Worth printing so an over-broad allowlist is visible in the log.
        print(f"  note  links.js allows {host!r}, which the map does not currently cite")
    print(f"  link hosts OK — {len(cited)} cited host(s), all permitted")
    return 0


def main() -> None:
    print("Extension manifest\n")
    errors = check_manifest()
    print("\nNavigation allowlist parity\n")
    errors += check_allowlist_matches_registry()
    print("\nBundled offline registry\n")
    errors += check_bundled_actions_current()
    print("\nSource link host parity\n")
    errors += check_source_link_hosts()
    print("\nRequest limit parity\n")
    errors += check_request_limits_match()
    print("\nStatic hygiene\n")
    errors += check_no_stale_references()

    print()
    if errors:
        sys.exit(f"FAILED: {errors} problem(s).")
    print("OK — minimal permissions, allowlist matches the registry.")


if __name__ == "__main__":
    main()
