"""End-to-end auth + history tests against a real Postgres.

Run separately from the unit tests (module-level app config is read from the environment):
    TEST_DATABASE_URL=postgresql://... pytest tests/test_db_integration.py
Skipped when TEST_DATABASE_URL is not set.
"""
import asyncio
import os
import sys
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
    import jwt
    from fastapi.testclient import TestClient

    from app import main

GOOD = dict(SEX=1, AGE=52, RACE="Black", BMI=31.0, WAIST=106, SYSBP=134, DIABP=84, GLUCOSE=104, HDL=38, TG=168, BPMEDS=0, DIABETES=0)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app, base_url="https://testserver") as c:
        yield c


PW = "correct-horse-9"


def _signin(client, email, pw=PW):
    r = client.post("/auth/signin", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _user(client, tag):
    email = f"{tag}-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": PW, "name": tag})
    assert r.status_code == 200, r.text
    assert "token" not in r.json()  # signup never issues a session
    return email, _bearer(_signin(client, email))


def _sql(query, *args):
    async def go():
        conn = await asyncpg.connect(URL)
        try:
            return await conn.fetch(query, *args)
        finally:
            await conn.close()
    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    main._buckets.clear()


def test_signup_signin_me(client):
    email, h = _user(client, "alice")
    assert client.post("/auth/signin", json={"email": email, "password": "wrong-password"}).status_code == 401
    assert client.get("/auth/me", headers=h).json()["email"] == email


# ---- signup does not reveal whether an email is registered
def test_signup_response_is_identical_for_new_and_existing_email(client):
    email = f"enum-{uuid.uuid4().hex[:8]}@example.com"
    first = client.post("/auth/signup", json={"email": email, "password": PW, "name": "Real Owner"})
    again = client.post("/auth/signup", json={"email": email, "password": "attacker-chosen-1", "name": "Mallory"})
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json() and "token" not in again.json()
    # the second call changed nothing: the owner's password and name still stand
    assert client.post("/auth/signin", json={"email": email, "password": "attacker-chosen-1"}).status_code == 401
    assert client.post("/auth/signin", json={"email": email, "password": PW}).json()["name"] == "Real Owner"
    assert _sql("SELECT count(*) AS n FROM users WHERE email = $1", email)[0]["n"] == 1


def test_signin_unknown_email_looks_like_wrong_password(client):
    email, _ = _user(client, "known")
    wrong = client.post("/auth/signin", json={"email": email, "password": "not-the-password"})
    unknown = client.post("/auth/signin", json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "not-the-password"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()


# ---- token revocation
def test_logout_revokes_only_that_token(client):
    email, h1 = _user(client, "lo")
    h2 = _bearer(_signin(client, email))  # a second device
    assert client.get("/auth/me", headers=h1).status_code == 200
    assert client.post("/auth/logout", headers=h1).status_code == 204
    assert client.get("/auth/me", headers=h1).status_code == 401
    assert client.get("/auth/me", headers=h2).status_code == 200


def test_logout_is_idempotent_and_tolerates_dead_tokens(client):
    _, h = _user(client, "idem")
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert client.post("/auth/logout", headers=h).status_code == 204  # already revoked
    assert client.post("/auth/logout").status_code == 204  # no token at all
    assert client.post("/auth/logout", headers=_bearer("garbage")).status_code == 204


def test_logout_all_kills_every_token_but_new_signins_work(client):
    email, h1 = _user(client, "all")
    h2 = _bearer(_signin(client, email))
    assert client.post("/auth/logout-all", headers=h1).status_code == 204
    assert client.get("/auth/me", headers=h1).status_code == 401
    assert client.get("/auth/me", headers=h2).status_code == 401
    assert client.get("/auth/me", headers=_bearer(_signin(client, email))).status_code == 200
    assert client.post("/auth/logout-all").status_code == 401  # needs a live session


def test_revoked_token_cannot_read_or_save_history(client):
    _, h = _user(client, "rv")
    assert client.post("/predict", json=GOOD, headers=h).json()["assessment_id"]
    client.post("/auth/logout", headers=h)
    assert client.get("/assessments", headers=h).status_code == 401
    after = client.post("/predict", json=GOOD, headers=h)  # still works, but anonymously: nothing saved
    assert after.status_code == 200 and after.json()["assessment_id"] is None


def _forge(**claims):
    now = datetime.now(timezone.utc)
    base = {"iat": now, "exp": now + timedelta(hours=1)}
    return jwt.encode({**base, **claims}, main.JWT_SECRET, algorithm="HS256")


def test_tokens_missing_revocation_claims_are_rejected(client):
    email, _ = _user(client, "legacy")
    uid = str(_sql("SELECT id FROM users WHERE email = $1", email)[0]["id"])
    legacy = _forge(sub=uid, email=email)  # what the pre-revocation API issued
    assert client.get("/auth/me", headers=_bearer(legacy)).status_code == 401
    good_shape = _forge(sub=uid, email=email, jti=str(uuid.uuid4()), tv=0)
    assert client.get("/auth/me", headers=_bearer(good_shape)).status_code == 200  # control: the forge helper is valid
    wrong_version = _forge(sub=uid, email=email, jti=str(uuid.uuid4()), tv=99)
    assert client.get("/auth/me", headers=_bearer(wrong_version)).status_code == 401


def test_expired_token_is_rejected(client):
    email, _ = _user(client, "exp")
    uid = str(_sql("SELECT id FROM users WHERE email = $1", email)[0]["id"])
    now = datetime.now(timezone.utc)
    old = jwt.encode({"sub": uid, "email": email, "jti": str(uuid.uuid4()), "tv": 0,
                      "iat": now - timedelta(days=9), "exp": now - timedelta(days=1)}, main.JWT_SECRET, algorithm="HS256")
    assert client.get("/auth/me", headers=_bearer(old)).status_code == 401


def test_session_lifetime_is_seven_days_by_default(client):
    email, _ = _user(client, "ttl")
    p = jwt.decode(_signin(client, email), main.JWT_SECRET, algorithms=["HS256"])
    assert p["exp"] - p["iat"] == 7 * 24 * 3600 and p["tv"] == 0 and uuid.UUID(p["jti"])


def test_expired_revocation_rows_are_purged(client):
    email, h = _user(client, "purge")
    uid = _sql("SELECT id FROM users WHERE email = $1", email)[0]["id"]
    stale = uuid.uuid4()
    _sql("INSERT INTO revoked_tokens (jti, user_id, expires_at) VALUES ($1, $2, NOW() - INTERVAL '1 day')", stale, uid)
    client.post("/auth/logout", headers=h)
    assert _sql("SELECT 1 FROM revoked_tokens WHERE jti = $1", stale) == []
    assert len(_sql("SELECT 1 FROM revoked_tokens WHERE user_id = $1", uid)) == 1


def test_save_list_delete_and_isolation(client):
    _, a = _user(client, "a")
    _, b = _user(client, "b")
    saved = client.post("/predict", json=GOOD, headers=a).json()
    assert saved["assessment_id"] and saved["model_version"].startswith("1.")
    assert client.post("/predict?save=false", json=GOOD, headers=a).json()["assessment_id"] is None
    rows = client.get("/assessments", headers=a).json()
    assert len(rows) == 1 and rows[0]["model_version"].startswith("1.") and rows[0]["inputs"]["AGE"] == 52
    assert client.get("/assessments", headers=b).json() == []
    assert client.delete(f"/assessments/{saved['assessment_id']}", headers=b).status_code == 404  # not theirs
    assert client.delete("/assessments/not-a-uuid", headers=a).status_code == 404
    assert client.delete(f"/assessments/{saved['assessment_id']}", headers=a).status_code == 204
    assert client.get("/assessments", headers=a).json() == []


def test_out_of_scope_and_invalid_are_not_saved(client):
    _, h = _user(client, "c")
    assert client.post("/predict", json={**GOOD, "PREGNANT": True}, headers=h).status_code == 422
    assert client.post("/predict", json={**GOOD, "AGE": 200}, headers=h).status_code == 422
    assert client.get("/assessments", headers=h).json() == []


def test_suspended_user_is_locked_out_immediately(client):
    email, h = _user(client, "d")
    _sql("UPDATE users SET is_active = false WHERE email = $1", email)
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.post("/auth/signin", json={"email": email, "password": "correct-horse-9"}).status_code == 403


def test_long_password_rejected_not_500(client):
    r = client.post("/auth/signup", json={"email": f"{uuid.uuid4().hex[:6]}@example.com", "password": "é" * 50})
    assert r.status_code == 422


# ------------------------------------------------------------------ change password (signed in)
NEW_PW = "battery-staple-77"


def _change(client, headers, current=PW, new=NEW_PW):
    return client.post("/auth/change-password", headers=headers, json={"current_password": current, "new_password": new})


def test_change_password_signs_out_other_sessions_and_keeps_this_one(client):
    email, here = _user(client, "chpw")
    elsewhere = _bearer(_signin(client, email))
    r = _change(client, here)
    assert r.status_code == 200, r.text
    fresh = _bearer(r.json()["token"])
    assert r.json()["email"] == email
    assert client.get("/auth/me", headers=fresh).status_code == 200  # this session carries on with the new token
    assert client.get("/auth/me", headers=here).status_code == 401  # the token it replaced is dead
    assert client.get("/auth/me", headers=elsewhere).status_code == 401  # every other session is signed out
    assert client.post("/auth/signin", json={"email": email, "password": PW}).status_code == 401
    assert _signin(client, email, NEW_PW)


def test_change_password_needs_the_current_password_and_changes_nothing_otherwise(client):
    email, here = _user(client, "chpwbad")
    elsewhere = _bearer(_signin(client, email))
    r = _change(client, here, current="not-my-password")
    assert r.status_code == 400 and "current password" in r.json()["detail"]
    assert client.get("/auth/me", headers=here).status_code == 200  # a wrong guess does not sign anyone out
    assert client.get("/auth/me", headers=elsewhere).status_code == 200
    assert client.post("/auth/signin", json={"email": email, "password": PW}).status_code == 200
    assert client.post("/auth/signin", json={"email": email, "password": NEW_PW}).status_code == 401


def test_change_password_rejects_same_short_long_and_anonymous(client):
    email, here = _user(client, "chpwval")
    assert _change(client, here, new=PW).status_code == 400  # same as the current one
    assert _change(client, here, new="short").status_code == 422
    assert _change(client, here, new="é" * 50).status_code == 422  # over bcrypt's 72 bytes, not a 500
    assert client.post("/auth/change-password", json={"current_password": PW, "new_password": NEW_PW}).status_code == 401
    assert client.post("/auth/signin", json={"email": email, "password": PW}).status_code == 200  # nothing changed


def test_change_password_attempts_are_limited_per_account_not_only_per_address(client, monkeypatch):
    monkeypatch.setitem(main.RATE_LIMITS, "/auth/change-password", (1000, 3600))  # isolate the per-account limit
    email, here = _user(client, "chpwrate")
    codes = [_change(client, here, current=f"wrong-guess-{i}").status_code for i in range(11)]
    assert codes[:10] == [400] * 10 and codes[10] == 429
    assert _change(client, here).status_code == 429  # even the right password is refused while limited
    assert client.post("/auth/signin", json={"email": email, "password": PW}).status_code == 200


# ------------------------------------------------------------------ session robustness
def test_api_answers_are_never_cacheable(client):
    email, h = _user(client, "nostore")
    for r in (client.get("/assessments", headers=h), client.get("/auth/me", headers=h),
              client.get("/assessments")):  # also the 401
        assert r.headers.get("cache-control") == "no-store", r.request.url
    assert "no-store" not in client.get("/").headers.get("cache-control", "")  # the app shell is still cacheable


def test_small_clock_differences_do_not_end_a_fresh_session(client):
    email, _ = _user(client, "skew")
    uid = str(_sql("SELECT id FROM users WHERE email = $1", email)[0]["id"])
    now = datetime.now(timezone.utc)
    ahead = jwt.encode({"sub": uid, "email": email, "jti": str(uuid.uuid4()), "tv": 0, "iat": now + timedelta(seconds=10),
                        "exp": now + timedelta(hours=1)}, main.JWT_SECRET, algorithm="HS256")
    assert client.get("/auth/me", headers=_bearer(ahead)).status_code == 200  # issued 10 s "in the future"
    way_ahead = jwt.encode({"sub": uid, "email": email, "jti": str(uuid.uuid4()), "tv": 0, "iat": now + timedelta(minutes=10),
                            "exp": now + timedelta(hours=1)}, main.JWT_SECRET, algorithm="HS256")
    assert client.get("/auth/me", headers=_bearer(way_ahead)).status_code == 401  # but not minutes
