"""Tests for admin login: bcrypt hashing, signed sessions, gating, rate limit.

Model-free and fast (a couple of bcrypt hashes). No network, no LLM.
"""

import time

import pytest
from fastapi import HTTPException

from ritaj import adminauth, api
from ritaj.config import settings


@pytest.fixture(autouse=True)
def _fixed_secret(monkeypatch):
    # Deterministic signing key so tokens verify within a test run.
    monkeypatch.setattr(settings, "session_secret", "test-signing-secret")
    monkeypatch.setattr(settings, "session_ttl_hours", 12)
    adminauth._fails.clear()


# --- password hashing --------------------------------------------------------


def test_hash_verify_roundtrip():
    h = adminauth.hash_password("Correct Horse 9!")
    assert h.startswith("$2") and len(h) >= 59
    assert adminauth.verify_password("Correct Horse 9!", h)
    assert not adminauth.verify_password("wrong", h)


def test_hash_is_salted_unique():
    assert adminauth.hash_password("same") != adminauth.hash_password("same")


def test_long_password_not_truncated():
    # bcrypt truncates >72 bytes; pre-hashing must make the full password count.
    a = "A" * 72 + "distinct-tail-1"
    b = "A" * 72 + "distinct-tail-2"
    h = adminauth.hash_password(a)
    assert adminauth.verify_password(a, h)
    assert not adminauth.verify_password(b, h)


def test_verify_password_handles_garbage_hash():
    assert not adminauth.verify_password("x", "not-a-bcrypt-hash")


# --- user store --------------------------------------------------------------


def test_load_users_parses_comma_and_newline(monkeypatch):
    h1, h2 = adminauth.hash_password("p1"), adminauth.hash_password("p2")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h1}, bob:{h2}")
    users = adminauth.load_users()
    assert set(users) == {"alice", "bob"}
    monkeypatch.setattr(settings, "admin_users", f"alice:{h1}\nbob:{h2}")
    assert set(adminauth.load_users()) == {"alice", "bob"}


def test_load_users_empty(monkeypatch):
    monkeypatch.setattr(settings, "admin_users", "")
    assert adminauth.load_users() == {}


def test_authenticate(monkeypatch):
    h = adminauth.hash_password("s3cret!!")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    assert adminauth.authenticate("alice", "s3cret!!")
    assert not adminauth.authenticate("alice", "nope")
    assert not adminauth.authenticate("ghost", "whatever")


# --- session tokens ----------------------------------------------------------


def test_session_roundtrip(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, exp = adminauth.issue_session("alice")
    assert exp > int(time.time())
    assert adminauth.verify_session(token) == "alice"


def test_session_tamper_rejected(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, _ = adminauth.issue_session("alice")
    payload, _, sig = token.partition(".")
    assert adminauth.verify_session(f"{payload}.{sig}x") is None       # bad sig
    assert adminauth.verify_session("garbage") is None
    assert adminauth.verify_session("") is None


def test_session_expiry(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, _ = adminauth.issue_session("alice", ttl_hours=-1)  # already expired
    assert adminauth.verify_session(token) is None


def test_session_wrong_signing_key_rejected(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, _ = adminauth.issue_session("alice")
    monkeypatch.setattr(settings, "session_secret", "different-key")
    assert adminauth.verify_session(token) is None


def test_session_for_removed_user_rejected(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, _ = adminauth.issue_session("alice")
    monkeypatch.setattr(settings, "admin_users", "")  # account revoked
    assert adminauth.verify_session(token) is None


# --- rate limiting -----------------------------------------------------------


def test_rate_limit_trips_after_five():
    key = "1.2.3.4:alice"
    for _ in range(5):
        assert not adminauth.rate_limited(key)
        adminauth.record_fail(key)
    assert adminauth.rate_limited(key)
    adminauth.clear_fails(key)
    assert not adminauth.rate_limited(key)


# --- gating (require_admin) --------------------------------------------------


class _Req:
    def __init__(self, headers=None, ip="1.2.3.4"):
        self.headers = headers or {}
        self.client = type("C", (), {"host": ip})()


def test_require_admin_accounts_mode(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    token, _ = adminauth.issue_session("alice")
    api.require_admin(_Req({"x-admin-token": token}))                 # ok
    api.require_admin(_Req({"authorization": f"Bearer {token}"}))     # ok
    with pytest.raises(HTTPException):
        api.require_admin(_Req({}))
    with pytest.raises(HTTPException):
        api.require_admin(_Req({"x-admin-token": "bogus"}))


def test_require_admin_accounts_take_precedence_over_legacy(monkeypatch):
    h = adminauth.hash_password("pw")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    monkeypatch.setattr(settings, "admin_token", "legacy-token")
    # Legacy token must NOT work once accounts exist.
    with pytest.raises(HTTPException):
        api.require_admin(_Req({"x-admin-token": "legacy-token"}))


# --- login route (integration) ----------------------------------------------


def _client():
    from starlette.testclient import TestClient
    return TestClient(api.app)


def test_login_route_success_and_failure(monkeypatch):
    h = adminauth.hash_password("s3cret!!")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    c = _client()

    r = c.post("/admin/login", json={"username": "alice", "password": "s3cret!!"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert adminauth.verify_session(token) == "alice"

    # The token now opens a gated route.
    assert c.get("/admin/me", headers={"X-Admin-Token": token}).json()["username"] == "alice"
    assert c.get("/admin/me").status_code == 401

    assert c.post("/admin/login", json={"username": "alice", "password": "wrong"}).status_code == 401


def test_login_disabled_without_accounts(monkeypatch):
    monkeypatch.setattr(settings, "admin_users", "")
    assert _client().post("/admin/login", json={"username": "a", "password": "b"}).status_code == 404


def test_login_rate_limited(monkeypatch):
    h = adminauth.hash_password("s3cret!!")
    monkeypatch.setattr(settings, "admin_users", f"alice:{h}")
    c = _client()
    for _ in range(5):
        c.post("/admin/login", json={"username": "alice", "password": "wrong"})
    r = c.post("/admin/login", json={"username": "alice", "password": "s3cret!!"})
    assert r.status_code == 429  # locked out even with the right password
