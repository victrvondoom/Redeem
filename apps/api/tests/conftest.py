import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="redeem-test-")
os.environ["REDEEM_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ.setdefault("REDEEM_ALLOW_FAULT_INJECTION", "true")
os.environ["REDEEM_DATA_DIR"] = f"{_tmp}/data"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import limiter  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


class Api:
    """TestClient wrapper that carries the CSRF token like the real frontend does."""

    def __init__(self, email="a@example.com", name="Asha", language="en"):
        self.c = TestClient(app)
        r = self.c.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery",
                                                       "name": name, "language": language})
        assert r.status_code == 201, r.text
        self.me = r.json()
        self.csrf = self.me["csrf_token"]

    def _h(self):
        return {"X-CSRF-Token": self.csrf}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self._h(), **kw)

    def put(self, url, json=None):
        return self.c.put(url, json=json, headers=self._h())

    def patch(self, url, json=None):
        return self.c.patch(url, json=json, headers=self._h())

    def delete(self, url):
        return self.c.delete(url, headers=self._h())


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    for k, v in dict(bolna_api_key="", bolna_agent_id="", bolna_webhook_secret="", allow_outbound_calls=False,
                     outbound_test_numbers="", allow_fault_injection=True).items():
        setattr(settings, k, v)
    yield


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def api2():
    return Api(email="b@example.com", name="Bala")


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def approve_all(api, mission):
    items = [{"action_id": a["id"], "digest": a["digest"]} for a in mission["plan"]["actions"]
             if a["status"] == "AWAITING_APPROVAL"]
    return api.post(f"/api/v1/missions/{mission['id']}/approve", {"approvals": items})


def pick(api, mission, label_part, role=None):
    cl = mission["clarification"]
    cand = next(c for c in cl["candidates"] if label_part in c["label"])
    return api.post(f"/api/v1/missions/{mission['id']}/bind", {"role": role or cl["role"], "value": cand["id"]}).json()
