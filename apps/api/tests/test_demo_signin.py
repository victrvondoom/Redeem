from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_demo_sign_in_gives_an_isolated_seeded_workspace_each_time():
    a, b = TestClient(app), TestClient(app)
    ra, rb = a.post("/api/v1/auth/demo"), b.post("/api/v1/auth/demo")
    assert ra.status_code == 201 and rb.status_code == 201
    assert ra.json()["tenant_id"] != rb.json()["tenant_id"] and ra.json()["email"].endswith("@demo.redeem.invalid")
    assert a.get("/api/v1/auth/me").json()["name"] == "Demo user"  # a real session was opened


def test_demo_sign_in_is_off_when_demo_fixtures_are_off(monkeypatch):
    monkeypatch.setenv("REDEEM_ENV", "production")
    monkeypatch.delenv("REDEEM_DEMO_FIXTURES", raising=False)
    assert settings.demo_enabled is False
    r = TestClient(app).post("/api/v1/auth/demo")
    assert r.status_code == 404 and r.json()["error"]["code"] == "demo_disabled"
