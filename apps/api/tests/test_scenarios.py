"""Scenario catalog tests. Headless: the API and database only (no desktop). Live execution is covered in test_portal_live.py."""
import datetime as dt

import pytest
from sqlalchemy import select

from app.computer import scenarios as SC
from app.computer import vision
from app.db import SessionLocal
from app.models import ComputerScenario, ComputerSession, ComputerTask

from conftest import Api

NEW = {"key": "my-check", "name": "My check", "category": "ops", "required_os": "windows", "required_capabilities": ["screen_observation"],
       "parameter_schema": {"type": "object", "properties": {"x": {"type": "string"}}}, "steps": [{"op": "observe_screen"}, {"op": "verify_text", "target": "Welcome"}],
       "executor": None, "reason": "first version"}


def items(api, **q):
    return api.get("/api/v1/computer/scenarios", params=q).json()["items"]


def test_builtin_catalog_comes_from_database_and_never_run_is_null():
    a = Api()
    its = items(a)
    keys = {i["key"] for i in its}
    assert {"crm-operator", "file-explorer-pdf", "consumer-case-portal"} <= keys
    assert all(i["last_run"] is None and i["run_count"] == 0 for i in its)  # nothing ever ran: no invented success
    with SessionLocal() as db:
        assert db.scalar(select(ComputerScenario).where(ComputerScenario.key == "crm-operator")).tenant_id is None
    by = {i["key"]: i for i in its}
    assert by["crm-operator"]["runnable"] and by["consumer-case-portal"]["runnable"]
    assert not by["file-explorer-pdf"]["runnable"] and "not implement" in by["file-explorer-pdf"]["unavailable_reason"]
    assert not by["user-takeover"]["runnable"]


FAR = dt.datetime(2999, 1, 1, tzinfo=dt.timezone.utc)


def _task(tenant, **kw):
    with SessionLocal() as db:
        s = ComputerSession(tenant_id=tenant, user_id="u", device_id="dev_x", mode="cloud", expires_at=FAR)
        db.add(s)
        db.flush()
        t = ComputerTask(tenant_id=tenant, session_id=s.id, instruction="x", **kw)
        db.add(t)
        db.commit()
        return t.id, s.id


def test_last_run_status_is_derived_from_computer_tasks():
    a = Api()
    tenant = a.me["tenant_id"]
    sc = next(i for i in items(a) if i["key"] == "crm-operator")
    old, _ = _task(tenant, scenario_id=sc["id"], status="FAILED", report={"summary": "boom"})
    new, _ = _task(tenant, scenario_id=sc["id"], status="DONE", report={"summary": "ok", "after_reload": [{"observed": True}, {"observed": True}]})
    got = next(i for i in items(a) if i["key"] == "crm-operator")
    assert got["last_run"]["task_id"] in (old, new) and got["run_count"] == 2
    # status transitions follow the row
    for raw, shown in [("PLANNING", "queued"), ("RUNNING", "running"), ("PAUSED", "paused"), ("USER_CONTROL", "paused"), ("NEEDS_APPROVAL", "waiting_for_approval"), ("DONE", "completed"),
                       ("FAILED", "failed"), ("STOPPED", "cancelled"), ("UNCERTAIN", "outcome_uncertain")]:
        with SessionLocal() as db:
            t = db.get(ComputerTask, new)
            t.status = raw
            t.created_at = FAR
            db.commit()
        lr = next(i for i in items(a) if i["key"] == "crm-operator")["last_run"]
        assert lr["status"] == shown and lr["raw_status"] == raw
    with SessionLocal() as db:
        t = db.get(ComputerTask, new)
        t.status = "DONE"
        db.commit()
    assert next(i for i in items(a) if i["key"] == "crm-operator")["last_run"]["verification_status"] == "verified"
    runs = a.get("/api/v1/computer/scenarios/crm-operator/runs").json()["items"]
    assert len(runs) == 2


def test_tasks_of_another_workspace_do_not_leak():
    a, b = Api("a@example.com"), Api("b@example.com")
    ta = a.me["tenant_id"]
    sc = next(i for i in items(a) if i["key"] == "crm-operator")
    _task(ta, scenario_id=sc["id"], status="DONE")
    assert next(i for i in items(a) if i["key"] == "crm-operator")["last_run"]
    assert next(i for i in items(b) if i["key"] == "crm-operator")["last_run"] is None


def test_scenario_crud_versions_enable_and_isolation():
    a, b = Api("a@example.com"), Api("b@example.com")
    r = a.post("/api/v1/computer/scenarios", NEW)
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 1 and r.json()["created_by"] == "a@example.com" and r.json()["built_in"] is False
    assert a.post("/api/v1/computer/scenarios", NEW).status_code == 409
    assert b.get("/api/v1/computer/scenarios/my-check").status_code == 404  # workspace isolation
    assert "my-check" not in {i["key"] for i in items(b)}
    e = a.put("/api/v1/computer/scenarios/my-check", {**NEW, "name": "My check v2", "reason": "rename"})
    assert e.status_code == 200 and e.json()["version"] == 2
    vs = a.get("/api/v1/computer/scenarios/my-check/versions").json()["items"]
    assert [v["version"] for v in vs] == [2, 1] and vs[1]["snapshot"]["name"] == "My check" and vs[0]["reason"] == "rename"
    assert a.post("/api/v1/computer/scenarios/my-check/enabled", {"enabled": False}).status_code == 200
    assert next(i for i in items(a) if i["key"] == "my-check")["enabled"] is False
    assert a.put("/api/v1/computer/scenarios/my-check", {**NEW, "key": "other"}).status_code == 422
    # built-ins cannot be changed by a workspace
    assert a.put("/api/v1/computer/scenarios/crm-operator", {**NEW, "key": "crm-operator"}).status_code == 403
    assert a.post("/api/v1/computer/scenarios/crm-operator/enabled", {"enabled": False}).status_code == 403


@pytest.mark.parametrize("bad", [
    {"steps": [{"op": "exec_python", "target": "import os"}]},
    {"steps": [{"op": "observe_screen", "code": "rm -rf /"}]},
    {"required_os": "beos"},
    {"required_capabilities": ["root"]},
    {"parameter_schema": {"type": "nonsense"}},
    {"key": "bad key!"},
])
def test_definitions_reject_code_and_unknown_vocabulary(bad):
    a = Api()
    assert a.post("/api/v1/computer/scenarios", {**NEW, **bad}).status_code == 422


def test_filters_search_and_viewer_cannot_edit():
    a = Api()
    a.post("/api/v1/computer/scenarios", NEW)
    assert {i["key"] for i in items(a, q="portal")} == {"consumer-case-portal"}
    assert {i["key"] for i in items(a, category="files")} == {"file-explorer-pdf"}
    assert "my-check" in {i["key"] for i in items(a, os="windows")} and "crm-operator" in {i["key"] for i in items(a, os="windows")}
    assert "my-check" not in {i["key"] for i in items(a, os="linux")}
    assert Api("z@example.com").get("/api/v1/computer/scenarios").status_code == 200


def test_unauthenticated_and_unrunnable_requests_are_refused():
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).get("/api/v1/computer/scenarios").status_code == 401
    a = Api()
    r = a.post("/api/v1/computer/scenarios/file-explorer-pdf/run", {"session_id": "cse_none", "params": {}})
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_implemented"  # honest: no pretend run
    assert a.post("/api/v1/computer/scenarios/user-takeover/run", {"session_id": "cse_none"}).status_code == 501
    assert a.post("/api/v1/computer/scenarios/crm-operator/run", {"session_id": "cse_none", "params": {"name": "Priya Sharma"}}).status_code == 404  # no such session


def test_parameter_validation_before_run():
    Api()
    with SessionLocal() as db:
        SC.seed(db)
        sc = db.scalar(select(ComputerScenario).where(ComputerScenario.key == "crm-operator"))
        with pytest.raises(SC.Invalid):
            SC.check_params(sc, {"name": "P"})
        with pytest.raises(SC.Invalid):
            SC.check_params(sc, {"name": "Priya Sharma", "method": "Carrier pigeon"})
        assert SC.check_params(sc, {"name": "Priya Sharma", "method": "WhatsApp"})


def test_vision_reports_unconfigured_honestly(monkeypatch):
    for k in ("REDEEM_VISION_PROVIDER", "REDEEM_VISION_API_KEY", "ANTHROPIC_API_KEY", "REDEEM_VISION_MODEL"):
        monkeypatch.delenv(k, raising=False)
    a = Api()
    v = a.get("/api/v1/computer/vision").json()
    assert v["configured"] is False and v["state"] == "PROVIDER_NOT_CONFIGURED" and v["connection_test"]["status"] == "not_run"
    modes = {m["id"]: m for m in v["perception"]}
    assert modes["ocr_grounding"]["kind"] == "non-LLM" and modes["vision_model"]["available"] is False
    assert a.get("/api/v1/computer/status").json()["vision_model"]["configured"] is False
    with pytest.raises(vision.NotConfigured):
        vision.plan(None, "x")
