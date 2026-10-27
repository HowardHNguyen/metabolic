"""Email verification and password reset against a real Postgres, using the in-memory "console" mail provider.

    TEST_DATABASE_URL=postgresql://... pytest tests/test_email_integration.py
Skipped when TEST_DATABASE_URL is not set.
"""
import asyncio
import hashlib
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

if URL:
    os.environ["DATABASE_URL"] = URL
    os.environ["JWT_SECRET"] = "test-secret-" + "x" * 52
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import asyncpg
    from fastapi.testclient import TestClient

    from app import emailer, main

PW, NEW_PW = "correct-horse-9", "battery-staple-77"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app, base_url="https://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _email_on(monkeypatch):
    monkeypatch.setattr(main, "EMAIL_MODE", "console")
    main._buckets.clear()
    emailer.OUTBOX.clear()


def _sql(query, *args):
    async def go():
        conn = await asyncpg.connect(URL)
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.close()
    return asyncio.run(go())


def _addr(tag):
    return f"{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _mails(email, subject_has=""):
    return [m for m in emailer.OUTBOX if m.to == email and subject_has in m.subject]


def _token(msg):
    return re.search(r"token=([A-Za-z0-9_\-]+)", msg.text).group(1)


def _signup(client, email, pw=PW, name=None):
    return client.post("/auth/signup", json={"email": email, "password": pw, "name": name})


def _signin(client, email, pw=PW):
    return client.post("/auth/signin", json={"email": email, "password": pw})


def _confirm(client, email):
    return client.post("/auth/verify-email", json={"token": _token(_mails(email, "Confirm")[-1])})


def _verified_user(client, tag="u"):
    email = _addr(tag)
    assert _signup(client, email).status_code == 200
    assert _confirm(client, email).status_code == 200
    return email


# ------------------------------------------------------------------ verification
def test_signup_needs_confirmation_before_signin(client):
    email = _addr("v")
    r = _signup(client, email)
    assert r.status_code == 200 and "token" not in r.json() and "Check your email" in r.json()["message"]
    blocked = _signin(client, email)
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "email_not_verified"
    assert _signin(client, email, "wrong-password").status_code == 401  # unconfirmed state is shown only with the right password
    msgs = _mails(email, "Confirm")
    assert len(msgs) == 1 and f"{main.APP_BASE_URL}/verify?token=" in msgs[0].text
    assert _confirm(client, email).status_code == 200
    assert _signin(client, email).status_code == 200
    assert _confirm(client, email).status_code == 400  # a link works once


def test_only_a_hash_of_the_token_is_stored(client):
    email = _addr("h")
    _signup(client, email)
    raw = _token(_mails(email)[-1])
    rows = _sql("SELECT token_hash FROM email_tokens t JOIN users u ON u.id = t.user_id WHERE u.email = $1", email)
    assert [r["token_hash"] for r in rows] == [hashlib.sha256(raw.encode()).hexdigest()]
    assert raw not in rows[0]["token_hash"]


def test_expired_confirmation_link_is_rejected(client):
    email = _addr("x")
    _signup(client, email)
    _sql("UPDATE email_tokens SET expires_at = NOW() - INTERVAL '1 minute' WHERE user_id = (SELECT id FROM users WHERE email = $1)", email)
    assert _confirm(client, email).status_code == 400
    assert _signin(client, email).status_code == 403


def test_signup_reply_is_identical_for_new_unconfirmed_and_confirmed_addresses(client):
    confirmed = _verified_user(client, "c")
    unconfirmed = _addr("p"); _signup(client, unconfirmed)
    replies = [_signup(client, e) for e in (confirmed, unconfirmed, _addr("n"))]
    assert {r.status_code for r in replies} == {200}
    assert len({str(r.json()) for r in replies}) == 1 and all("token" not in r.json() for r in replies)


def test_confirmed_account_is_never_changed_by_signup_and_owner_is_told(client):
    email = _verified_user(client, "own")
    assert _signup(client, email, "attacker-chosen-1", "Mallory").status_code == 200
    assert _signin(client, email, "attacker-chosen-1").status_code == 401
    assert _signin(client, email).status_code == 200
    notice = _mails(email, "already have")
    assert len(notice) == 1 and "/forgot" in notice[0].text and "#" not in notice[0].text and "token=" not in notice[0].text
    assert len(_mails(email, "Confirm")) == 1  # only the original confirmation, nothing new


def test_unconfirmed_address_cannot_be_squatted(client):
    victim = _addr("victim")
    _signup(client, victim, "attacker-pass-1")        # attacker registers the victim's address
    attacker_link = _token(_mails(victim, "Confirm")[-1])
    _signup(client, victim, PW)                       # the real owner signs up
    assert client.post("/auth/verify-email", json={"token": attacker_link}).status_code == 400  # superseded
    assert _confirm(client, victim).status_code == 200  # only the mailbox owner receives this link
    assert _signin(client, victim, "attacker-pass-1").status_code == 401
    assert _signin(client, victim, PW).status_code == 200


def test_resend_confirmation_is_uniform_and_only_mails_unconfirmed(client):
    pending, done, ghost = _addr("pend"), _verified_user(client, "done"), _addr("ghost")
    _signup(client, pending); emailer.OUTBOX.clear()
    replies = [client.post("/auth/resend-verification", json={"email": e}) for e in (pending, done, ghost)]
    assert {r.status_code for r in replies} == {200} and len({str(r.json()) for r in replies}) == 1
    assert len(_mails(pending, "Confirm")) == 1 and not _mails(done) and not _mails(ghost)
    assert _confirm(client, pending).status_code == 200


# ------------------------------------------------------------------ password reset
def test_forgot_password_reply_is_uniform_and_only_real_accounts_get_mail(client):
    known, ghost = _verified_user(client, "k"), _addr("nobody")
    emailer.OUTBOX.clear()
    a, b = (client.post("/auth/forgot-password", json={"email": e}) for e in (known, ghost))
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert len(_mails(known, "Reset")) == 1 and not _mails(ghost)


def test_reset_changes_password_signs_out_everywhere_and_link_is_single_use(client):
    email = _verified_user(client, "r")
    session = {"Authorization": "Bearer " + _signin(client, email).json()["token"]}
    assert client.get("/auth/me", headers=session).status_code == 200
    client.post("/auth/forgot-password", json={"email": email})
    link = _token(_mails(email, "Reset")[-1])
    done = client.post("/auth/reset-password", json={"token": link, "password": NEW_PW})
    assert done.status_code == 200
    assert _signin(client, email, PW).status_code == 401 and _signin(client, email, NEW_PW).status_code == 200
    assert client.get("/auth/me", headers=session).status_code == 401  # the old session is gone
    assert client.post("/auth/reset-password", json={"token": link, "password": "another-pass-1"}).status_code == 400
    assert _signin(client, email, NEW_PW).status_code == 200  # the replay changed nothing
    assert len(_mails(email, "was changed")) == 1


def test_newer_reset_link_supersedes_older_and_reset_voids_other_links(client):
    email = _verified_user(client, "s")
    client.post("/auth/forgot-password", json={"email": email}); first = _token(_mails(email, "Reset")[-1])
    client.post("/auth/forgot-password", json={"email": email}); second = _token(_mails(email, "Reset")[-1])
    assert client.post("/auth/reset-password", json={"token": first, "password": NEW_PW}).status_code == 400
    client.post("/auth/forgot-password", json={"email": email}); third = _token(_mails(email, "Reset")[-1])
    assert client.post("/auth/reset-password", json={"token": third, "password": NEW_PW}).status_code == 200
    assert client.post("/auth/reset-password", json={"token": second, "password": "x-another-pass"}).status_code == 400


def test_reset_confirms_an_unconfirmed_address(client):
    email = _addr("u"); _signup(client, email)
    assert _signin(client, email).status_code == 403
    client.post("/auth/forgot-password", json={"email": email})
    assert client.post("/auth/reset-password", json={"token": _token(_mails(email, "Reset")[-1]), "password": NEW_PW}).status_code == 200
    assert _signin(client, email, NEW_PW).status_code == 200


def test_reset_rejects_bad_requests_without_side_effects(client):
    email = _verified_user(client, "b")
    assert client.post("/auth/reset-password", json={"token": "A" * 43, "password": NEW_PW}).status_code == 400
    client.post("/auth/forgot-password", json={"email": email}); link = _token(_mails(email, "Reset")[-1])
    assert client.post("/auth/reset-password", json={"token": link, "password": "short"}).status_code == 422
    assert client.post("/auth/reset-password", json={"token": link, "password": "é" * 50}).status_code == 422
    _sql("UPDATE users SET is_active = false WHERE email = $1", email)  # suspended accounts cannot be reset into
    assert client.post("/auth/reset-password", json={"token": link, "password": NEW_PW}).status_code == 400
    _sql("UPDATE users SET is_active = true WHERE email = $1", email)
    assert _signin(client, email, PW).status_code == 200 and _signin(client, email, NEW_PW).status_code == 401
    assert client.post("/auth/reset-password", json={"token": link, "password": NEW_PW}).status_code == 200  # rolled back, so the link still works


def test_cannot_mail_bomb_an_address(client):
    # 5 requests stay under the per-IP limit (5/hour) so this isolates the per-address cap of 3 emails/hour/kind
    email = _verified_user(client, "bomb")
    emailer.OUTBOX.clear()
    for _ in range(5):
        assert client.post("/auth/forgot-password", json={"email": email}).status_code == 200
    assert len(_mails(email, "Reset")) == 3
    for _ in range(4):
        assert _signup(client, email).status_code == 200
    assert len(_mails(email, "already have")) == 3


def test_ip_rate_limit_on_forgot_password(client):
    codes = [client.post("/auth/forgot-password", json={"email": _addr("rl")}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


# ------------------------------------------------------------------ email switched off (the safe default)
def test_everything_still_works_with_email_off(client, monkeypatch):
    monkeypatch.setattr(main, "EMAIL_MODE", "")
    email = _addr("off")
    assert _signup(client, email).status_code == 200 and not emailer.OUTBOX
    assert _signin(client, email).status_code == 200  # verified immediately: nothing to wait for
    for path, body in (("/auth/forgot-password", {"email": email}), ("/auth/resend-verification", {"email": email}),
                       ("/auth/reset-password", {"token": "A" * 43, "password": NEW_PW})):
        assert client.post(path, json=body).status_code == 503
    assert client.get("/health").json()["email"] == "off"


# ------------------------------------------------------------------ schema migration and housekeeping
class _OneConn:  # minimal pool stand-in so _ensure_schema can run from the test thread
    def __init__(self, conn): self.conn = conn
    def acquire(self): return self
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *a): return False


def test_migration_grandfathers_existing_users_exactly_once(client):
    old = _verified_user(client, "old")
    async def migrate():
        conn = await asyncpg.connect(URL)
        try:
            await conn.execute("ALTER TABLE users DROP COLUMN email_verified_at")  # simulate the pre-feature schema
            await main._ensure_schema(_OneConn(conn))
            return await conn.fetchval("SELECT count(*) FROM users WHERE email_verified_at IS NULL")
        finally:
            await conn.close()
    assert asyncio.run(migrate()) == 0  # every existing account was grandfathered as confirmed
    fresh = _addr("fresh"); _signup(client, fresh)
    async def restart():
        conn = await asyncpg.connect(URL)
        try:
            await main._ensure_schema(_OneConn(conn))
        finally:
            await conn.close()
    asyncio.run(restart())
    assert _sql("SELECT email_verified_at FROM users WHERE email = $1", fresh)[0]["email_verified_at"] is None  # a restart does not confirm it
    assert _signin(client, old).status_code == 200


def test_abandoned_unconfirmed_accounts_and_old_tokens_are_cleaned_up(client):
    stale = _addr("stale"); _signup(client, stale)
    _sql("UPDATE users SET created_at = NOW() - INTERVAL '8 days' WHERE email = $1", stale)
    main._last_cleanup = float("-inf")
    _signup(client, _addr("trigger"))  # housekeeping runs as a background task after a signup
    for _ in range(50):  # the task may finish just after the response; give it up to 5 s
        if not _sql("SELECT 1 FROM users WHERE email = $1", stale):
            break
        time.sleep(0.1)
    assert _sql("SELECT 1 FROM users WHERE email = $1", stale) == []


def test_housekeeping_clocks_start_unthrottled_in_a_fresh_process():
    # regression: starting at 0.0 made the first run depend on how long the machine had been up
    import subprocess
    code = "import app.main as m; print(m._last_cleanup, m._last_sweep)"
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == ["-inf", "-inf"]


# ------------------------------------------------------------------ change password (signed in)
def test_change_password_emails_the_owner_and_voids_outstanding_reset_links(client):
    email = _verified_user(client, "cp")
    session = {"Authorization": "Bearer " + _signin(client, email).json()["token"]}
    client.post("/auth/forgot-password", json={"email": email})  # a reset link is now outstanding
    link = _token(_mails(email, "Reset")[-1])
    r = client.post("/auth/change-password", headers=session, json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200, r.text
    notice = _mails(email, "was changed")
    assert len(notice) == 1 and "other sessions were signed out" in notice[0].text
    assert "reset it now" in notice[0].text  # the owner can undo it if it was not them
    # the old reset link can no longer be used to take the account over
    assert client.post("/auth/reset-password", json={"token": link, "password": "another-pass-1"}).status_code == 400
    assert _signin(client, email, NEW_PW).status_code == 200


def test_change_password_works_with_email_off_and_sends_nothing(client, monkeypatch):
    email = _verified_user(client, "cpoff")
    session = {"Authorization": "Bearer " + _signin(client, email).json()["token"]}
    monkeypatch.setattr(main, "EMAIL_MODE", "")
    emailer.OUTBOX.clear()
    r = client.post("/auth/change-password", headers=session, json={"current_password": PW, "new_password": NEW_PW})
    assert r.status_code == 200 and not emailer.OUTBOX
