# ruff: noqa: F811  (pytest fixtures imported from test_computer are used as arguments)
"""LIVE-DESKTOP tests: the portal scenario runs on a real Xvfb display with real Chromium, the real bridge and real input injection.
Case data below is a test-only record created in an isolated database; it is not a customer case. The portal is REDEEM-owned (not an external filing)."""
import time

import httpx

import pytest
from sqlalchemy import select

from app.computer import portal
from app.db import SessionLocal
from app.models import PortalSubmission
from test_computer import Live, _cloud, needs_x, live, server  # noqa: F401,F811  (pytest fixtures)

TEXT = "My Jio postpaid bill shows Rs 1,299 of extra charges. Complaint no: CMP-8812 no resolution."


def _case(live):
    r = live.post("/api/v1/cases", {"text": TEXT})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_portal_http_contract_and_duplicate_prevention(server, live):
    """HTTP-level (not a UI test): validation, persistence, duplicate rejection, independent retrieval, tenant key isolation."""
    cid = _case(live)
    with SessionLocal() as db:
        key = portal.workspace_key(db, live.me["tenant_id"])
    base = f"{server}/portal/{key}"
    body = {"case_ref": cid, "department": "Billing", "claim_summary": "Extra charges on my bill", "amount_inr": "1299", "documents": ["bill.pdf"]}
    assert httpx.post(f"{base}/api/submissions", json={**body, "department": "Nope"}).status_code == 422
    assert httpx.post(f"{base}/api/submissions", json={**body, "amount_inr": "12,99"}).status_code == 422
    r = httpx.post(f"{base}/api/submissions", json=body)
    assert r.status_code == 201 and r.json()["acknowledgement_id"].startswith("RCP-") and r.json()["portal_response"]["external_filing"] is False
    d = httpx.post(f"{base}/api/submissions", json=body)
    assert d.status_code == 409 and d.json()["error"]["acknowledgement_id"] == r.json()["acknowledgement_id"]
    assert httpx.get(f"{base}/api/submissions/{r.json()['acknowledgement_id']}").json()["payload_digest"] == portal.payload_digest(portal.payload(cid, "Billing", "Extra charges on my bill", "1299", ["bill.pdf"]))
    assert httpx.get(f"{server}/portal/wrongkey/api/submissions").status_code == 404


@needs_x
def test_portal_scenario_fills_form_waits_for_exact_approval_then_submits(server, live):
    cid = _case(live)
    s = _cloud(live)
    sid = s["session"]["id"]
    r = live.post("/api/v1/computer/scenarios/consumer-case-portal/run", {"session_id": sid, "params": {"case_id": cid, "department": "Billing"}})
    assert r.status_code == 202, r.text
    tid = r.json()["id"]
    t = live.wait(tid)
    assert t["status"] == "NEEDS_APPROVAL", t["report"]
    pa = t["pending_approval"]
    assert pa["payload"]["case_ref"] == cid and pa["payload"]["department"] == "Billing" and pa["payload_digest"][:16] in pa["target"]["label"]
    with SessionLocal() as db:
        assert db.scalar(select(PortalSubmission)) is None  # nothing was submitted before approval
    assert live.post(f"/api/v1/computer/tasks/{tid}/approve", {"digest": "0" * 64}).status_code == 409
    assert live.post(f"/api/v1/computer/tasks/{tid}/approve", {"digest": pa["digest"]}).status_code == 200
    t = live.wait(tid)
    assert t["status"] == "DONE", t["report"]
    ack = t["report"]["acknowledgement_id"]
    with SessionLocal() as db:
        rows = list(db.scalars(select(PortalSubmission)))
        assert len(rows) == 1 and rows[0].acknowledgement_id == ack and rows[0].approval_ref == pa["digest"] and rows[0].payload_digest == pa["payload_digest"]
        assert rows[0].fields["department"] == "Billing" and rows[0].fields["case_ref"] == cid
    kinds = {a["action"] for a in t["actions"]}
    assert kinds <= {"observe_screen", "open_url", "click_element", "type_text", "key_combination"}  # filled and submitted by UI interaction only
    assert any(a["target"] and a["target"]["label"].startswith("Submit request") for a in t["actions"] if a["action"] == "click_element")
    # scenario catalog now shows this real run
    sc = live.get("/api/v1/computer/scenarios/consumer-case-portal").json()
    assert sc["last_run"]["task_id"] == tid and sc["last_run"]["status"] == "completed" and sc["last_run"]["verification_status"] == "verified"
    # running the same payload again reconciles instead of resending
    t2 = live.wait(live.post("/api/v1/computer/scenarios/consumer-case-portal/run", {"session_id": sid, "params": {"case_id": cid, "department": "Billing"}}).json()["id"])
    assert t2["status"] == "DONE" and "already received" in t2["report"]["summary"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(PortalSubmission)))) == 1


@needs_x
def test_changing_a_field_after_approval_invalidates_it(server, live):
    cid = _case(live)
    sid = _cloud(live)["session"]["id"]
    t = live.wait(live.post("/api/v1/computer/scenarios/consumer-case-portal/run", {"session_id": sid, "params": {"case_id": cid, "department": "Billing"}}).json()["id"])
    old = t["pending_approval"]["digest"]
    # a different department is a different payload: a new run needs its own approval, the old digest is refused
    t2 = live.wait(live.post("/api/v1/computer/scenarios/consumer-case-portal/run", {"session_id": sid, "params": {"case_id": cid, "department": "Escalations"}}).json()["id"]) if \
        live.post(f"/api/v1/computer/tasks/{t['id']}/reject").status_code == 200 else None
    assert t2 and t2["status"] == "NEEDS_APPROVAL" and t2["pending_approval"]["digest"] != old
    assert live.post(f"/api/v1/computer/tasks/{t2['id']}/approve", {"digest": old}).status_code == 409


def test_case_of_another_workspace_is_not_found(server, live):
    other = Live(server, f"o{time.time_ns()}@example.com")
    cid = _case(other)
    sid = None
    r = live.post("/api/v1/computer/scenarios/consumer-case-portal/run", {"session_id": sid or "cse_x", "params": {"case_id": cid}})
    assert r.status_code == 404  # session lookup fails first; case lookup is tenant-filtered in intent_for
    with SessionLocal() as db:
        from app.computer import agent
        with pytest.raises(agent.BadParams):
            agent.intent_for("portal_case", {"case_id": cid}, live.me["tenant_id"], db)
