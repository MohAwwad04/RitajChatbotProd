#!/usr/bin/env python3
"""Configure admin accounts on the Hugging Face Space (login-based /admin).

Interactively collects up to N admin usernames + passwords, bcrypt-hashes them
locally (raw passwords never leave this machine), and sets two Space secrets:
  • ADMIN_USERS   — "user:hash,user:hash,..." (hashes only)
  • SESSION_SECRET — a fresh random signing key (unless already provided)

Then restarts the Space so the new login takes effect. Requires an HF Write
token. See DEPLOYMENT.md.

Usage:
    HF_TOKEN=hf_xxx .venv/bin/python scripts/set_admins.py            # prompts for 3
    HF_TOKEN=hf_xxx .venv/bin/python scripts/set_admins.py --count 2
"""

import argparse
import os
import secrets
import sys
from getpass import getpass

# Import the project's hashing so the algorithm matches the server exactly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ritaj.adminauth import hash_password  # noqa: E402

SPACE_ID = "MohAwwad04/ritaj-rag"


def collect(count: int) -> str:
    entries = []
    seen = set()
    print(f"Enter {count} admin account(s). Passwords are hashed locally.\n")
    for i in range(1, count + 1):
        while True:
            username = input(f"[{i}/{count}] username: ").strip()
            if not username or ":" in username or "," in username:
                print("  username must be non-empty and contain no ':' or ','")
                continue
            if username in seen:
                print("  duplicate username")
                continue
            break
        while True:
            pw = getpass("        password: ")
            if len(pw) < 8:
                print("  use at least 8 characters")
                continue
            if pw != getpass("        confirm : "):
                print("  passwords do not match")
                continue
            break
        seen.add(username)
        entries.append(f"{username}:{hash_password(pw)}")
    return ",".join(entries)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (a Write token from huggingface.co/settings/tokens).")

    from huggingface_hub import add_space_secret, restart_space

    admin_users = collect(args.count)
    session_secret = os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(48)

    add_space_secret(SPACE_ID, "ADMIN_USERS", admin_users, token=token)
    add_space_secret(SPACE_ID, "SESSION_SECRET", session_secret, token=token)
    print(f"\nSet ADMIN_USERS ({args.count} account(s)) and SESSION_SECRET on {SPACE_ID}.")
    print("Restarting the Space…")
    restart_space(SPACE_ID, token=token)
    print("Done. The /admin console now uses username + password login.")


if __name__ == "__main__":
    main()
