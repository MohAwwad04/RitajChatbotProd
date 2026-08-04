"""Admin authentication: password login + signed session tokens.

Replaces the single shared ADMIN_TOKEN with per-user accounts. Credentials are
stored as **bcrypt hashes only** (never plaintext) in the ADMIN_USERS env var /
Space secret — one ``username:bcrypt_hash`` pair per line (or comma-separated).
A successful login mints a short-lived, HMAC-signed session token that the
console sends on every /admin/* call. The server stays stateless: nothing is
persisted per session, and revoking an account is just removing it from
ADMIN_USERS (any live token for it stops verifying).

Security choices:
  • bcrypt for password hashing (per-hash salt, slow by design). Passwords are
    pre-hashed with SHA-256 first so bcrypt's 72-byte input limit never
    truncates a long passphrase.
  • Session tokens are ``base64url(payload).base64url(HMAC-SHA256)`` with an
    expiry; verification is constant-time (hmac.compare_digest).
  • Login is rate-limited per (IP, username) to blunt brute force.
  • User lookups run a dummy bcrypt check on miss to flatten timing (no
    username enumeration).

Generate a hash for a new account without the raw password ever touching disk
or your shell history / this chat:

    python -m ritaj.adminauth hash alice
    # prompts for the password twice, prints  alice:$2b$12$....
"""

import base64
import hashlib
import hmac
import json
import secrets
import sys
import time
from getpass import getpass

import bcrypt

from .config import settings

# --- password hashing -------------------------------------------------------


def _prep(password: str) -> bytes:
    """bcrypt silently truncates input at 72 bytes; pre-hash so the whole
    password is used regardless of length (base64 of SHA-256 = 44 bytes)."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    """Return a bcrypt hash (with embedded salt) for storage in ADMIN_USERS."""
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# A fixed hash to check against on a missing user, so a wrong username costs the
# same time as a wrong password (no enumeration via response timing).
_DUMMY_HASH = bcrypt.hashpw(_prep("dummy-password"), bcrypt.gensalt())


# --- user store -------------------------------------------------------------


def load_users() -> dict[str, str]:
    """Parse ADMIN_USERS into {username: bcrypt_hash}.

    Accepts newline- or comma-separated ``username:hash`` entries. bcrypt hashes
    contain no ':' or ',', so each entry is split on the first ':' only.
    """
    raw = settings.admin_users or ""
    users: dict[str, str] = {}
    for entry in (e.strip() for e in raw.replace("\n", ",").split(",")):
        if not entry or ":" not in entry:
            continue
        name, _, h = entry.partition(":")
        name, h = name.strip(), h.strip()
        if name and h:
            users[name] = h
    return users


def authenticate(username: str, password: str) -> bool:
    """True iff the username exists and the password matches its stored hash."""
    hashed = load_users().get(username)
    if hashed is None:
        bcrypt.checkpw(_prep(password), _DUMMY_HASH)  # equalize timing
        return False
    return verify_password(password, hashed)


# --- session tokens ---------------------------------------------------------

# If SESSION_SECRET is unset, use a random per-process key: tokens verify within
# a single run but every restart invalidates them. Set SESSION_SECRET in prod.
_EPHEMERAL_SECRET = secrets.token_bytes(32)


def _signing_key() -> bytes:
    return settings.session_secret.encode("utf-8") if settings.session_secret else _EPHEMERAL_SECRET


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    return _b64e(hmac.new(_signing_key(), payload_b64.encode("ascii"), hashlib.sha256).digest())


def issue_session(username: str, ttl_hours: int | None = None) -> tuple[str, int]:
    """Mint a signed session token for ``username``; returns (token, expiry_ts)."""
    ttl = (settings.session_ttl_hours if ttl_hours is None else ttl_hours) * 3600
    now = int(time.time())
    exp = now + ttl
    payload = _b64e(json.dumps({"u": username, "iat": now, "exp": exp}, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}", exp


def verify_session(token: str) -> str | None:
    """Return the username if ``token`` is a valid, unexpired session for a
    still-existing account; otherwise None."""
    if not token or token.count(".") != 1:
        return None
    payload, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(_b64d(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    username = data.get("u")
    # Revocation: a token stops working the moment its account leaves ADMIN_USERS.
    if not username or username not in load_users():
        return None
    return username


# --- login rate limiting (in-memory, per process) ---------------------------

_MAX_FAILS = 5
_WINDOW_SECONDS = 300
_fails: dict[str, list[float]] = {}


def _recent(key: str, now: float) -> list[float]:
    return [t for t in _fails.get(key, []) if now - t < _WINDOW_SECONDS]


def rate_limited(key: str) -> bool:
    now = time.time()
    recent = _recent(key, now)
    _fails[key] = recent
    return len(recent) >= _MAX_FAILS


def record_fail(key: str) -> None:
    now = time.time()
    _fails[key] = _recent(key, now) + [now]


def clear_fails(key: str) -> None:
    _fails.pop(key, None)


# --- CLI: hash a password for ADMIN_USERS -----------------------------------


def _cli() -> None:
    args = sys.argv[1:]
    if not args or args[0] != "hash":
        print(__doc__)
        return
    username = (args[1] if len(args) > 1 else input("username: ")).strip()
    if not username or ":" in username or "," in username:
        sys.exit("username must be non-empty and contain no ':' or ','")
    pw = getpass("password: ")
    if len(pw) < 8:
        sys.exit("use at least 8 characters")
    if pw != getpass("confirm : "):
        sys.exit("passwords do not match")
    print("\nAdd this to ADMIN_USERS (comma-separate multiple accounts):\n")
    print(f"{username}:{hash_password(pw)}")


if __name__ == "__main__":
    _cli()
