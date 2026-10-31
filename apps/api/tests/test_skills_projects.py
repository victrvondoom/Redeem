import time

import pytest

from app.resolve import browser as rb

needs_browser = pytest.mark.skipif(not rb.browser_available()[0], reason="Chromium not available")

CRM_TASK = [{"op": "goto", "app": "crm", "path": "/"}, {"op": "wait_text", "text": "Create follow-up task"},
            {"op": "fill", "label": "Contact ID", "value": "{{contact}}"}, {"op": "fill", "label": "Task title", "value": "{{title}}"},
            {"op": "click", "button": "Create task"}, {"op": "wait_text", "text": "Task created"}]


def _tasks(api):
    w = rb.world_for(api.me["tenant_id"] if "tenant_id" in api.me else api.get("/api/v1/auth/me").json()["tenant_id"])
    return rb.get_json(w.crm.url + "/api/tasks")


def test_skill_validation_rejects_unsafe_steps(api):
    bad = [[{"op": "goto", "app": "evil", "path": "/"}], [{"op": "goto", "app": "crm", "path": "//evil.example"}],
           [{"op": "click", "button": "x"}], [{"op": "goto", "app": "crm", "path": "/"}, {"op": "eval", "js": "1"}]]
    for steps in bad:
        assert api.post("/api/v1/browser/skills/record", {"name": "x", "steps": steps}).status_code == 422
    r = api.post("/api/v1/browser/skills/record", {"name": "x", "steps": CRM_TASK, "params": {"contact": "C-104"}})
    assert r.status_code == 422 and "title" in r.json()["error"]["message"]


@needs_browser
def test_record_replay_persists_real_state_and_frames(api, api2):
    r = api.post("/api/v1/browser/skills/record", {"name": "CRM follow-up", "steps": CRM_TASK, "params": {"contact": "C-104", "title": "Recorded once"}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recording"]["status"] == "DONE" and body["skill"]["params"] == ["contact", "title"]
    assert len(body["recording"]["frames"]) == len(CRM_TASK)
    sid = body["skill"]["id"]
    run = api.post(f"/api/v1/browser/skills/{sid}/run", {"params": {"contact": "C-208", "title": "Replayed"}, "background": False}).json()
    assert run["status"] == "DONE" and run["step_index"] == len(CRM_TASK)
    titles = [t["title"] for t in _tasks(api)]
    assert "Recorded once" in titles and "Replayed" in titles          # independent read of the app's own API, not the UI toast
    png = api.get(run["frames"][-1]["screenshot_url"])
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    # tenant isolation
    assert api2.get(f"/api/v1/browser/skills/{sid}").status_code == 404
    assert api2.get(f"/api/v1/browser/skill-runs/{run['id']}").status_code == 404
    assert api2.post(f"/api/v1/browser/skills/{sid}/run", {"params": {}}).status_code == 404
    assert api2.get(run["frames"][-1]["screenshot_url"]).status_code == 404
    assert api.get(f"/api/v1/browser/skills/{sid}").json()["runs"] == 2


@needs_browser
def test_failed_replay_after_click_is_uncertain_and_not_retried(api):
    sid = api.post("/api/v1/browser/skills/record", {"name": "t", "steps": CRM_TASK, "params": {"contact": "C-104", "title": "a"}}).json()["skill"]["id"]
    run = api.post(f"/api/v1/browser/skills/{sid}/run", {"params": {"contact": "C-999", "title": "b"}, "background": False}).json()
    assert run["status"] == "FAILED" and run["uncertain"] is True and "step 6" in run["error"]
    assert "b" not in [t["title"] for t in _tasks(api)]


@needs_browser
def test_live_run_pause_resume_stop(api):
    sid = api.post("/api/v1/browser/skills/record", {"name": "t", "steps": CRM_TASK, "params": {"contact": "C-104", "title": "a"}}).json()["skill"]["id"]
    run = api.post(f"/api/v1/browser/skills/{sid}/run", {"params": {"contact": "C-104", "title": "live"}}).json()
    assert api.post(f"/api/v1/browser/skills/{sid}/run", {"params": {"contact": "C-104", "title": "x"}}).status_code == 409
    assert api.post(f"/api/v1/browser/skill-runs/{run['id']}/control", {"action": "pause"}).status_code == 200
    deadline = time.time() + 20
    while time.time() < deadline and api.get(f"/api/v1/browser/skill-runs/{run['id']}").json()["status"] != "PAUSED":
        time.sleep(0.2)
    paused = api.get(f"/api/v1/browser/skill-runs/{run['id']}").json()
    assert paused["status"] == "PAUSED"
    time.sleep(1.0)
    assert api.get(f"/api/v1/browser/skill-runs/{run['id']}").json()["step_index"] == paused["step_index"]   # no progress while paused
    api.post(f"/api/v1/browser/skill-runs/{run['id']}/control", {"action": "stop"})
    while time.time() < deadline and api.get(f"/api/v1/browser/skill-runs/{run['id']}").json()["status"] in ("PAUSED", "RUNNING"):
        time.sleep(0.2)
    final = api.get(f"/api/v1/browser/skill-runs/{run['id']}").json()
    assert final["status"] == "STOPPED" and final["step_index"] < len(CRM_TASK)
    assert api.post(f"/api/v1/browser/skill-runs/{run['id']}/control", {"action": "resume"}).status_code == 409


def test_project_store_crud_and_idor(api, api2):
    p = api.post("/api/v1/projects", {"name": "Refund for July trip", "description": "airline + hotel"}).json()
    doc = api.post("/api/v1/documents", files={"file": ("a.txt", b"receipt 1200 INR", "text/plain")})
    assert doc.status_code == 201, doc.text
    did = doc.json().get("id") or doc.json().get("document", {}).get("id")
    assert api.post(f"/api/v1/projects/{p['id']}/items", {"kind": "document", "ref_id": did}).status_code == 201
    assert api.post(f"/api/v1/projects/{p['id']}/items", {"kind": "document", "ref_id": did}).status_code == 409
    got = api.get(f"/api/v1/projects/{p['id']}").json()
    assert got["items"][0]["title"] == "a.txt" and not got["items"][0]["missing"]
    assert api.get("/api/v1/projects").json()["items"][0]["items"] == 1
    assert api.get("/api/v1/projects?q=July").json()["items"] and not api.get("/api/v1/projects?q=zzz").json()["items"]
    # IDOR: another tenant can neither read the project nor attach its own or this tenant's objects
    assert api2.get(f"/api/v1/projects/{p['id']}").status_code == 404
    assert api2.post(f"/api/v1/projects/{p['id']}/items", {"kind": "document", "ref_id": did}).status_code == 404
    p2 = api2.post("/api/v1/projects", {"name": "mine"}).json()
    assert api2.post(f"/api/v1/projects/{p2['id']}/items", {"kind": "document", "ref_id": did}).status_code == 404
    assert api2.delete(f"/api/v1/projects/{p['id']}").status_code == 404
    assert api.patch(f"/api/v1/projects/{p['id']}", {"name": "Renamed"}).json()["name"] == "Renamed"
    item = got["items"][0]["id"]
    assert api.delete(f"/api/v1/projects/{p['id']}/items/{item}").status_code == 204
    assert api.delete(f"/api/v1/projects/{p['id']}").status_code == 204
    assert api.get(f"/api/v1/projects/{p['id']}").status_code == 404
    exp = api2.get("/api/v1/privacy/export").json()["projects"]
    assert [x["name"] for x in exp] == ["mine"]
