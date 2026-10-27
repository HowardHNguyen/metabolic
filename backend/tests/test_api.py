import pytest

from app import main


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["features"] == 12


def test_predict_ok(client, good):
    r = client.post("/predict?save=false", json=good)
    assert r.status_code == 200
    j = r.json()
    assert 0 < j["risk_probability"] < 1 and j["category"] in {"low", "borderline", "intermediate", "high"}
    assert j["model_version"].startswith("1.")
    assert j["criteria"]["met"] == 5 and j["criteria"]["verdict"] == "meets"
    assert set(j["percentiles"]["values"]) == {"WAIST", "BMI", "GLUCOSE", "HDL", "TG"}


def test_quick_screen_needs_no_labs(client, good):
    quick = {k: good[k] for k in ("SEX", "AGE", "RACE", "BMI", "WAIST")}
    j = client.post("/predict?save=false", json=quick).json()
    assert j["criteria"]["unknown"] == 4 and j["criteria"]["verdict"] == "incomplete"
    assert j["risk_probability"] == client.post("/predict?save=false", json=good).json()["risk_probability"]


def test_race_is_optional(client, good):
    good.pop("RACE")
    assert client.post("/predict?save=false", json=good).status_code == 200


def test_float_sex_and_extra_keys_accepted(client, good):
    r = client.post("/predict?save=false", json={**good, "SEX": 1.0, "TOTCHOL": 200, "educ": 2})
    assert r.status_code == 200


@pytest.mark.parametrize("bad", [
    {"AGE": -5}, {"AGE": 19}, {"AGE": 81}, {"SYSBP": 9999}, {"BMI": 0}, {"WAIST": 20}, {"WAIST": 400}, {"SEX": 3},
    {"DIABETES": 2}, {"GLUCOSE": 5}, {"TG": 1e9}, {"HDL": 1}, {"DIABP": 150, "SYSBP": 140}, {"RACE": "Martian"},
    {"SYSBP": None},
])
def test_rejects_implausible_input(client, good, bad):
    assert client.post("/predict?save=false", json={**good, **bad}).status_code == 422


@pytest.mark.parametrize("field", ["WAIST", "BMI", "AGE", "SEX"])
def test_missing_required_field(client, good, field):
    good.pop(field)
    assert client.post("/predict?save=false", json=good).status_code == 422


def test_pregnancy_is_out_of_scope(client, good):
    r = client.post("/predict?save=false", json={**good, "SEX": 2, "PREGNANT": True})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "out_of_scope"


def test_scenarios_reduce_risk(client, good):
    j = client.post("/scenarios", json=good).json()
    assert j["scenarios"] and all(s["delta_pp"] <= 0 for s in j["scenarios"])
    assert j["scenarios"][-1]["name"] == "Both together"
    assert j["scenarios"][-1]["delta_pp"] <= min(s["delta_pp"] for s in j["scenarios"][:-1]) + 1e-9


def test_criteria_endpoint(client, good):
    j = client.post("/criteria", json={**good, "BPMEDS": 1, "SYSBP": None, "DIABP": None}).json()
    bp = next(c for c in j["criteria"] if c["id"] == "bp")
    assert bp["status"] == "met" and "medicine" in bp["reason"]


def test_explain_shape(client, good):
    j = client.post("/explain", json=good).json()
    assert {c["feature"] for c in j["contributions"]} == {"AGE", "SEX", "RACE", "BMI", "WAIST"}
    assert j["contributions"][0]["abs_value"] >= j["contributions"][-1]["abs_value"]


def test_security_headers(client):
    h = client.get("/health").headers
    assert "max-age" in h["strict-transport-security"] and h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"]


def test_docs_hidden_by_default(client):
    # may be the SPA shell (200) when the frontend is built, but never Swagger / the OpenAPI schema
    assert "swagger" not in client.get("/docs").text.lower()
    assert '"openapi"' not in client.get("/openapi.json").text


def test_unknown_api_path_is_404_json_not_html(client):
    r = client.get("/predict/nope")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_signup_without_db_is_503(client):
    main._buckets.clear()
    r = client.post("/auth/signup", json={"email": "a@b.co", "password": "longenough1"})
    assert r.status_code == 503


def test_long_password_rejected(client):
    assert client.post("/auth/signup", json={"email": "a@b.co", "password": "x" * 100}).status_code == 422


def test_rate_limit_cannot_be_bypassed_with_forged_xff(client):
    main._buckets.clear()
    codes = []
    for i in range(8):  # attacker rotates the client-supplied (left-most) XFF entry; proxy appends the real IP
        r = client.post("/auth/signin", json={"email": "a@b.co", "password": "wrongpass"},
                        headers={"X-Forwarded-For": f"10.9.8.{i}, 203.0.113.7"})
        codes.append(r.status_code)
    assert 429 not in codes  # 8 attempts, under the limit of 10, despite 8 different forged addresses
    for i in range(5):
        r = client.post("/auth/signin", json={"email": "a@b.co", "password": "wrongpass"},
                        headers={"X-Forwarded-For": f"10.1.1.{i}, 203.0.113.7"})
    assert r.status_code == 429 and r.headers["retry-after"]
    main._buckets.clear()


def test_rate_limit_is_per_client(client):
    main._buckets.clear()
    for _ in range(10):
        client.post("/auth/signin", json={"email": "a@b.co", "password": "wrongpass"},
                    headers={"X-Forwarded-For": "198.51.100.1"})
    blocked = client.post("/auth/signin", json={"email": "a@b.co", "password": "wrongpass"},
                          headers={"X-Forwarded-For": "198.51.100.1"})
    other = client.post("/auth/signin", json={"email": "a@b.co", "password": "wrongpass"},
                        headers={"X-Forwarded-For": "198.51.100.2"})
    assert blocked.status_code == 429 and other.status_code != 429
    main._buckets.clear()


# ---------------------------------------------------------------- email (no database needed)
def test_email_is_off_by_default_and_features_report_unavailable(client):
    assert client.get("/health").json()["email"] == "off"
    for path, body in (("/auth/forgot-password", {"email": "a@b.co"}), ("/auth/resend-verification", {"email": "a@b.co"}),
                       ("/auth/reset-password", {"token": "A" * 43, "password": "long-enough-1"})):
        r = client.post(path, json=body)
        assert r.status_code == 503 and "not available" in r.json()["detail"]


def test_verify_email_without_database_is_503_not_500(client):
    assert client.post("/auth/verify-email", json={"token": "A" * 43}).status_code == 503


def test_misconfigured_provider_turns_email_off_instead_of_stopping_the_app(monkeypatch):
    monkeypatch.setattr(main, "EMAIL_PROVIDER", "acs")
    monkeypatch.setattr(main, "ACS_CONNECTION_STRING", "")
    monkeypatch.setattr(main, "EMAIL_FROM", "")
    assert main._resolve_email_mode() == ""
    monkeypatch.setattr(main, "ACS_CONNECTION_STRING", "endpoint=https://x.communication.azure.com/;accesskey=abc")
    assert main._resolve_email_mode() == ""  # sender address still missing
    monkeypatch.setattr(main, "EMAIL_FROM", "DoNotReply@example.azurecomm.net")
    assert main._resolve_email_mode() == "acs"
    monkeypatch.setattr(main, "EMAIL_PROVIDER", "mailgun-typo")
    assert main._resolve_email_mode() == ""


def test_acs_sender_builds_the_expected_request(monkeypatch):
    import sys
    import types
    sent = {}

    class FakeClient:
        @classmethod
        def from_connection_string(cls, cs):
            sent["cs"] = cs
            return cls()

        def begin_send(self, message):
            sent["message"] = message

    mod = types.ModuleType("azure.communication.email")
    mod.EmailClient = FakeClient
    for name in ("azure", "azure.communication"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "azure.communication.email", mod)
    from app import emailer
    msg = emailer.reset_message("person@example.com", "https://metabolic.vitalckm.com/reset?token=abc")
    emailer.acs_send(msg, "endpoint=https://x/;accesskey=k", "DoNotReply@x.azurecomm.net")
    m = sent["message"]
    assert sent["cs"].startswith("endpoint=") and m["senderAddress"] == "DoNotReply@x.azurecomm.net"
    assert m["recipients"]["to"] == [{"address": "person@example.com"}]
    assert "/reset?token=abc" in m["content"]["plainText"] and "/reset?token=abc" in m["content"]["html"]
    assert m["content"]["subject"]


def test_delivery_failure_never_raises(monkeypatch):
    monkeypatch.setattr(main, "EMAIL_MODE", "acs")
    monkeypatch.setattr(main.emailer, "acs_send", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")))
    main._deliver(main.emailer.Message("a@b.co", "s", "t", "h"))  # logged, not raised


def test_email_templates_contain_the_link_once_and_escape_html():
    from app import emailer
    url = "https://metabolic.vitalckm.com/verify?token=abc_DEF-123"
    for msg in (emailer.verify_message("a@b.co", url), emailer.reset_message("a@b.co", url)):
        assert msg.text.count(url) == 1 and url in msg.html
    assert "<script>" not in emailer.verify_message("a@b.co", 'https://x/"><script>alert(1)</script>').html


def test_change_password_requires_sign_in_and_is_rate_limited(client):
    body = {"current_password": "whatever-1", "new_password": "another-pass-1"}
    assert client.post("/auth/change-password", json=body).status_code == 401
    assert "/auth/change-password" in main.RATE_LIMITS


def test_email_links_carry_no_url_fragment():
    """Some mail apps drop everything after '#', so links are plain path + query."""
    assert main._link("verify", "tok123") == f"{main.APP_BASE_URL}/verify?token=tok123"
    assert main._link("reset", "tok123") == f"{main.APP_BASE_URL}/reset?token=tok123"
    assert main._link("forgot") == f"{main.APP_BASE_URL}/forgot"
    assert "#" not in main._link("signin") + main._link("verify", "t")
