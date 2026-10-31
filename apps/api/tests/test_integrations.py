"""Contract tests for the Google adapter against an in-process fake of Google's documented endpoints.
These prove REDEEM's behaviour (OAuth state, encryption, approval, idempotency, reconcile-not-resend, revocation, isolation).
They are NOT evidence of a live Google connection; see tests/live (skipped without credentials)."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import text

from app.config import settings
from app.integrations import google as g
from app.integrations import service as svc

B = "/api/v1"
CAL_P = {"summary": "Refund call with airline", "start": "2026-11-02T10:00:00", "end": "2026-11-02T10:30:00", "timezone": "Asia/Kolkata", "attendees": ["a@example.com"]}
MAIL_P = {"to": ["family@example.com"], "subject": "Flight update", "body": "My flight FA2041 was cancelled; refund requested."}


class FakeGoogle:
    def __init__(self):
        self.events, self.messages, self.inserts, self.sends, self.refreshes, self.revoked = {}, {}, 0, 0, 0, []
        self.drop_response_once = False
        self.bad_refresh = False
        self.no_refresh_token = False
        self.expires_in = 3600
        self.scope = "openid email https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"

    def handler(self, req: httpx.Request) -> httpx.Response:
        u = req.url
        if u.host == "oauth2.googleapis.com" and u.path == "/token":
            f = parse_qs(req.content.decode())
            if f["grant_type"][0] == "authorization_code":
                if f["code"][0] != "good-code":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                t = {"access_token": "acc-1", "expires_in": self.expires_in, "scope": self.scope}
                if not self.no_refresh_token:
                    t["refresh_token"] = "ref-secret-1"
                return httpx.Response(200, json=t)
            self.refreshes += 1
            if self.bad_refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": f"acc-{1 + self.refreshes}", "expires_in": self.expires_in})
        if u.path == "/revoke":
            self.revoked.append(parse_qs(req.content.decode())["token"][0])
            return httpx.Response(200)
        if u.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"email": "asha@example.com"})
        if req.headers.get("authorization", "") == "":
            return httpx.Response(401, json={})
        if u.path.endswith("/calendars/primary/events") and req.method == "POST":
            body = json.loads(req.content)
            if body["id"] in self.events:
                return httpx.Response(409, json={"error": {"message": "exists"}})
            self.events[body["id"]] = {**body, "status": "confirmed"}
            self.inserts += 1
            if self.drop_response_once:
                self.drop_response_once = False
                raise httpx.ReadTimeout("lost reply", request=req)
            return httpx.Response(200, json=self.events[body["id"]])
        if "/calendars/primary/events/" in u.path and req.method == "GET":
            ev = self.events.get(u.path.rsplit("/", 1)[1])
            return httpx.Response(200, json=ev) if ev else httpx.Response(404, json={})
        if u.path.endswith("/messages/send"):
            import base64
            raw = base64.urlsafe_b64decode(json.loads(req.content)["raw"] + "==").decode()
            mid = next(line.split(":", 1)[1].strip() for line in raw.splitlines() if line.lower().startswith("message-id"))
            self.sends += 1
            gid = f"gm{self.sends}"
            self.messages[gid] = {"id": gid, "labelIds": ["SENT"], "mid": mid}
            if self.drop_response_once:
                self.drop_response_once = False
                raise httpx.ReadTimeout("lost reply", request=req)
            return httpx.Response(200, json={"id": gid, "labelIds": ["SENT"]})
        if u.path.endswith("/gmail/v1/users/me/messages") and req.method == "GET":
            q = parse_qs(u.query.decode())["q"][0].removeprefix("rfc822msgid:")
            hits = [{"id": m["id"]} for m in self.messages.values() if m["mid"].strip("<>") == q]
            return httpx.Response(200, json={"messages": hits} if hits else {})
        if "/messages/" in u.path and req.method == "GET":
            m = self.messages.get(u.path.rsplit("/", 1)[1])
            return httpx.Response(200, json=m) if m else httpx.Response(404, json={})
        return httpx.Response(404, json={})


@pytest.fixture
def fake(monkeypatch):
    f = FakeGoogle()
    monkeypatch.setattr(settings, "google_client_id", "cid-123")
    monkeypatch.setattr(settings, "google_client_secret", "csecret-xyz")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://redeem.test/api/v1/integrations/google/callback")
    monkeypatch.setattr(svc, "make_google", lambda: g.GoogleClient("cid-123", "csecret-xyz", "https://redeem.test/api/v1/integrations/google/callback", 5.0, transport=httpx.MockTransport(f.handler)))
    monkeypatch.setattr(g.time, "sleep", lambda s: None)
    return f


def connect(api, caps=("calendar", "email")):
    url = api.post(f"{B}/integrations/google/connect", {"capabilities": list(caps)}).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = api.c.get(f"{B}/integrations/google/callback?state={state}&code=good-code", follow_redirects=False)
    return url, state, r


def draft(api, kind="calendar.create_event", params=None):
    r = api.post(f"{B}/integrations/actions", {"kind": kind, "params": params or (CAL_P if kind.startswith("calendar") else MAIL_P)})
    assert r.status_code == 201, r.text
    return r.json()


def run(api, a):
    api.post(f"{B}/integrations/actions/{a['id']}/approve", {"digest": a["digest"]})
    return api.post(f"{B}/integrations/actions/{a['id']}/execute").json()


def test_unconfigured_provider_is_reported_honestly_and_nothing_pretends(api):
    st = {p["provider"]: p for p in api.get(f"{B}/integrations").json()["providers"]}
    assert st["google"]["state"] == "not_configured" and st["google"]["missing_config"] == ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"]
    assert st["google"]["live_verified"] is False and st["bolna"]["state"] == "not_configured" and st["bolna"]["live_verified"] is False
    assert api.post(f"{B}/integrations/google/connect", {"capabilities": ["calendar"]}).json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert api.post(f"{B}/integrations/actions", {"kind": "email.send", "params": MAIL_P}).status_code == 409


def test_oauth_flow_state_is_single_use_bound_to_the_user_and_tokens_are_encrypted(api, api2, fake, db):
    url, state, r = connect(api)
    q = parse_qs(urlparse(url).query)
    assert url.startswith(g.AUTH) and q["client_id"] == ["cid-123"] and q["access_type"] == ["offline"] and "calendar.events" in q["scope"][0] and "gmail.send" in q["scope"][0]
    assert r.status_code == 302 and r.headers["location"] == "/app/connections?connected=google"
    st = {p["provider"]: p for p in api.get(f"{B}/integrations").json()["providers"]}["google"]
    assert st["state"] == "connected" and st["account"] == "asha@example.com" and st["live_verified"] and "https://www.googleapis.com/auth/calendar.events" in st["scopes"]
    raw = db.execute(text("select token_enc from integrations")).scalar()
    assert raw.startswith("enc2t:") and "ref-secret-1" not in raw and "acc-1" not in raw
    assert "ref-secret-1" not in api.get(f"{B}/integrations").text and "acc-1" not in api.get(f"{B}/integrations").text
    again = api.c.get(f"{B}/integrations/google/callback?state={state}&code=good-code", follow_redirects=False)
    assert "error=invalid_state" in again.headers["location"]                                       # single use
    url2 = api2.post(f"{B}/integrations/google/connect", {"capabilities": ["calendar"]}).json()["auth_url"]
    st2 = parse_qs(urlparse(url2).query)["state"][0]
    assert "error=invalid_state" in api.c.get(f"{B}/integrations/google/callback?state={st2}&code=good-code", follow_redirects=False).headers["location"]   # someone else's state
    assert "error=invalid_state" in api.c.get(f"{B}/integrations/google/callback?state=forged&code=good-code", follow_redirects=False).headers["location"]


def test_bad_code_and_missing_offline_access_do_not_connect(api, fake):
    url = api.post(f"{B}/integrations/google/connect", {"capabilities": ["calendar"]}).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert "error=provider_auth" in api.c.get(f"{B}/integrations/google/callback?state={state}&code=bad", follow_redirects=False).headers["location"]
    fake.no_refresh_token = True
    _, _, r = connect(api)
    assert "error=no_refresh_token" in r.headers["location"]
    assert {p["provider"]: p for p in api.get(f"{B}/integrations").json()["providers"]}["google"]["state"] == "not_connected"


def test_calendar_event_is_approved_executed_once_and_verified_by_read_back(api, fake):
    connect(api)
    a = draft(api)
    assert a["status"] == "DRAFT" and api.post(f"{B}/integrations/actions/{a['id']}/execute").json()["error"]["code"] == "invalid_state"       # no execution without approval
    assert api.post(f"{B}/integrations/actions/{a['id']}/approve", {"digest": "0" * 64}).json()["error"]["code"] == "stale_approval"
    done = run(api, a)
    assert done["status"] == "VERIFIED" and done["verification"]["found"] and done["verification"]["summary_matches"] and fake.inserts == 1
    assert api.post(f"{B}/integrations/actions/{a['id']}/execute").json()["error"]["code"] == "invalid_state" and fake.inserts == 1               # never twice


def test_lost_reply_on_calendar_insert_is_uncertain_then_reconciled_without_a_second_event(api, fake):
    connect(api)
    a = draft(api)
    fake.drop_response_once = True
    done = run(api, a)
    assert done["status"] == "UNCERTAIN" and done["error"].startswith("outcome_unknown") and fake.inserts == 1
    assert api.post(f"{B}/integrations/actions/{a['id']}/execute").status_code == 409
    rec = api.post(f"{B}/integrations/actions/{a['id']}/reconcile").json()
    assert rec["status"] == "VERIFIED" and fake.inserts == 1 and len(fake.events) == 1


def test_email_send_is_verified_and_a_lost_reply_is_reconciled_by_message_id_never_resent(api, fake):
    connect(api)
    ok = run(api, draft(api, "email.send"))
    assert ok["status"] == "VERIFIED" and ok["verification"]["labelled_sent"] and fake.sends == 1
    fake.drop_response_once = True
    lost = run(api, draft(api, "email.send"))
    assert lost["status"] == "UNCERTAIN" and fake.sends == 2
    rec = api.post(f"{B}/integrations/actions/{lost['id']}/reconcile").json()
    assert rec["status"] == "VERIFIED" and fake.sends == 2                                      # found by Message-ID, nothing resent


def test_reconcile_with_nothing_at_the_provider_ends_as_failed_not_as_success(api, fake):
    connect(api)
    a = draft(api, "email.send")
    api.post(f"{B}/integrations/actions/{a['id']}/approve", {"digest": a["digest"]})
    from app.db import SessionLocal
    from app.models import ExternalAction
    with SessionLocal() as s:                     # outcome unknown but the provider never received it
        s.get(ExternalAction, a["id"]).status = "UNCERTAIN"
        s.commit()
    rec = api.post(f"{B}/integrations/actions/{a['id']}/reconcile").json()
    assert rec["status"] == "FAILED" and rec["error"] == "not_found_at_provider" and fake.sends == 0


def test_expired_access_token_is_refreshed_and_a_revoked_grant_requires_reauthorization(api, fake):
    fake.expires_in = 1                             # access token already stale
    connect(api)
    assert run(api, draft(api))["status"] == "VERIFIED" and fake.refreshes >= 1
    fake.bad_refresh = True
    bad = run(api, draft(api, "email.send"))
    assert bad["status"] == "FAILED" and bad["error"] == "reauthorization_required" and fake.sends == 0
    st = {p["provider"]: p for p in api.get(f"{B}/integrations").json()["providers"]}["google"]
    assert st["state"] == "error" and st["last_error"] == "reauthorization_required"


def test_disconnect_revokes_at_google_clears_tokens_and_stops_queued_actions(api, fake, db):
    connect(api)
    queued = draft(api)
    out = api.post(f"{B}/integrations/google/disconnect").json()
    assert out["revoked_at_provider"] is True and fake.revoked == ["ref-secret-1"] and out["queued_actions_stopped"] == 1
    assert api.get(f"{B}/integrations/actions/{queued['id']}").json()["status"] == "FAILED"
    assert "ref-secret-1" not in db.execute(text("select token_enc from integrations")).scalar()
    assert api.post(f"{B}/integrations/actions", {"kind": "email.send", "params": MAIL_P}).status_code == 409


def test_scope_isolation_idor_and_validation(api, api2, fake):
    fake.scope = "openid email https://www.googleapis.com/auth/calendar.events"
    connect(api, ("calendar",))
    assert api.post(f"{B}/integrations/actions", {"kind": "email.send", "params": MAIL_P}).json()["error"]["code"] == "missing_scope"
    a = draft(api)
    for call in (lambda: api2.get(f"{B}/integrations/actions/{a['id']}"), lambda: api2.post(f"{B}/integrations/actions/{a['id']}/approve", {"digest": a["digest"]}),
                 lambda: api2.post(f"{B}/integrations/actions/{a['id']}/execute"), lambda: api2.post(f"{B}/integrations/actions/{a['id']}/reconcile")):
        assert call().status_code == 404
    assert api2.get(f"{B}/integrations/actions").json()["items"] == [] and len(api.get(f"{B}/integrations/actions").json()["items"]) == 1
    assert api2.post(f"{B}/integrations/google/test").status_code == 409
    assert api.post(f"{B}/integrations/actions", {"kind": "email.send", "params": {"to": ["not-an-address"], "subject": "x", "body": "y"}}).status_code == 422
    assert api.post(f"{B}/integrations/actions", {"kind": "calendar.create_event", "params": MAIL_P}).status_code == 422


def test_connection_test_hits_the_provider_and_records_verification(api, fake):
    connect(api)
    assert api.post(f"{B}/integrations/google/test").json()["ok"] is True


@pytest.mark.skipif(not __import__("os").environ.get("GOOGLE_TEST_REFRESH_TOKEN"), reason="live Google test needs GOOGLE_OAUTH_CLIENT_ID/SECRET and GOOGLE_TEST_REFRESH_TOKEN")
def test_live_google_refresh_and_userinfo():
    import os
    cl = g.GoogleClient(os.environ["GOOGLE_OAUTH_CLIENT_ID"], os.environ["GOOGLE_OAUTH_CLIENT_SECRET"], os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", ""))
    tok = cl.refresh(os.environ["GOOGLE_TEST_REFRESH_TOKEN"])
    assert cl.userinfo(tok["access_token"]).get("email")


def test_production_mode_never_seeds_simulated_data_and_disables_demo_runs(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import FxBooking
    from app.db import SessionLocal
    monkeypatch.setenv("REDEEM_ENV", "production")
    monkeypatch.setenv("REDEEM_MASTER_KEY", "A" * 43)
    from app.security import vault
    vault.reset_for_tests()
    c = TestClient(app)
    r = c.post(f"{B}/auth/register", json={"email": "prod@example.com", "password": "correct-horse-battery", "name": "Prod"})
    assert r.status_code == 201
    with SessionLocal() as s:
        assert s.query(FxBooking).count() == 0
    h = {"x-csrf-token": r.json()["csrf_token"]}
    assert c.post(f"{B}/demo/scenarios/a/run", headers=h).json()["error"]["code"] == "demo_disabled"
    assert c.get(f"{B}/health").json()["demo_fixtures"] is False
    vault.reset_for_tests()
