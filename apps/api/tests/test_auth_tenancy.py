from conftest import Api, approve_all, pick


def test_register_login_logout_and_session(api):
    assert api.get("/api/v1/auth/me").json()["email"] == "a@example.com"
    api.post("/api/v1/auth/logout")
    assert api.get("/api/v1/auth/me").status_code == 401
    r = api.c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200 and "redeem_session" in r.cookies or api.c.cookies.get("redeem_session")
    bad = api.c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password-x"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"


def test_weak_password_and_duplicate_email_rejected(api):
    r = api.c.post("/api/v1/auth/register", json={"email": "z@example.com", "password": "short", "name": "Z"})
    assert r.status_code == 422
    r = api.c.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "another-long-pass", "name": "Z"})
    assert r.status_code == 409


def test_cookie_is_httponly_and_csrf_enforced(api):
    r = api.c.post("/api/v1/missions", json={"intent": "my flight was cancelled"})  # no CSRF header
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = api.c.post("/api/v1/missions", json={"intent": "my flight was cancelled"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    login = api.c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert "httponly" in login.headers["set-cookie"].lower()


def test_unauthenticated_requests_blocked():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    for path in ("/api/v1/missions", "/api/v1/documents", "/api/v1/voice/calls", "/api/v1/quality", "/api/v1/domains"):
        assert c.get(path).status_code == 401, path


def test_cross_tenant_isolation(api, api2):
    m = api.post("/api/v1/missions", {"intent": "My flight was cancelled and refund hasn't come"}).json()
    # IDOR on every mission sub-resource
    for method, path, body in [("get", "", None), ("get", "/events", None), ("get", "/receipt", None),
                               ("post", "/cancel", {}), ("post", "/execute", {}), ("post", "/revise", {"intent": "hack"}),
                               ("post", "/bind", {"role": "booking_id", "value": "x"}),
                               ("post", "/faults", {"kind": "ack_loss"})]:
        r = getattr(api2, method)(f"/api/v1/missions/{m['id']}{path}", *([body] if method == "post" else []))
        assert r.status_code == 404, (path, r.status_code)
    assert api2.get("/api/v1/missions").json()["total"] == 0
    # B cannot bind A's booking into B's own mission
    mb = api2.post("/api/v1/missions", {"intent": "flight cancelled refund please"}).json()
    foreign = m["clarification"]["candidates"][0]["id"]
    r = api2.post(f"/api/v1/missions/{mb['id']}/bind", {"role": "booking_id", "value": foreign})
    assert r.status_code == 404
    # documents
    d = api.post("/api/v1/documents", files={"file": ("t.txt", b"PNR FA2041", "text/plain")})
    assert d.status_code == 201
    doc_id = d.json()["id"]
    assert api2.get(f"/api/v1/documents/{doc_id}/download").status_code == 404
    assert api2.delete(f"/api/v1/documents/{doc_id}").status_code == 404
    assert api2.get("/api/v1/documents").json()["items"] == []
    r = api2.post("/api/v1/missions", {"intent": "flight cancelled refund", "document_id": doc_id})
    assert r.status_code == 404


def test_revoked_connector_stops_actions(api):
    m = api.post("/api/v1/missions", {"intent": "Flight FA2041 cancelled, need refund"}).json()
    assert m["status"] == "NEEDS_APPROVAL"
    assert approve_all(api, m).status_code == 200
    assert api.post("/api/v1/connectors/booking_fixture/revoke").status_code == 200
    out = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    assert out["status"] in ("FAILED", "PARTIALLY_VERIFIED")
    assert all(a["status"] == "BLOCKED" for a in out["plan"]["actions"])
    events = [e["type"] for e in api.get(f"/api/v1/missions/{m['id']}/events").json()["items"]]
    assert "CONNECTOR_REVOKED" in events and "DISPATCHING" not in events


def test_deleted_account_loses_access(api, api2):
    api.post("/api/v1/missions", {"intent": "flight cancelled refund"})
    assert api.delete("/api/v1/users/me").status_code == 204
    assert api.get("/api/v1/auth/me").status_code == 401
    r = api.c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 401
    assert api2.get("/api/v1/missions").status_code == 200  # other tenant unaffected


def test_rate_limit_on_login(api):
    codes = [api.c.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope-nope-nope"}).status_code
             for _ in range(10)]
    assert 429 in codes


def test_privacy_export_and_delete_mission(api):
    m = api.post("/api/v1/missions", {"intent": "flight cancelled refund"}).json()
    exp = api.get("/api/v1/privacy/export").json()
    assert any(x["id"] == m["id"] for x in exp["missions"])
    assert api.delete(f"/api/v1/privacy/missions/{m['id']}").status_code == 204
    assert api.get(f"/api/v1/missions/{m['id']}").status_code == 404


def test_registration_is_rate_limited_per_ip():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    codes = [c.post("/api/v1/auth/register", json={"email": f"r{i}@example.com", "password": "correct-horse-battery", "name": "R"}).status_code
             for i in range(12)]
    assert codes[:10] == [201] * 10 and 429 in codes[10:]
