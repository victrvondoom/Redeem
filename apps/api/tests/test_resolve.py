import sqlite3

import pytest

from app.orchestration import agents, utterance
from app.resolve import browser as rb
from conftest import approve_all

B = "/api/v1"
FOLLOW = "Prepare a follow-up for Jordan Lee using the latest report, update the CRM and send it after I approve."


def truth(tenant, app, kind):
    w = rb.world_for(tenant)
    with sqlite3.connect(str(getattr(w, app).db_path)) as db:
        return db.execute("SELECT detail FROM ground_truth WHERE kind=?", (kind,)).fetchall()


def start(api, bind="C-104"):
    m = api.post(f"{B}/missions", {"intent": FOLLOW}).json()
    assert m["status"] == "DISCOVERING" and m["clarification"]["type"] == "entity_ambiguous"
    cand = next(c for c in m["clarification"]["candidates"] if bind in c["label"])
    return api.post(f"{B}/missions/{m['id']}/bind", {"role": "contact_id", "value": cand["id"]}).json()


def run(api, m):
    approve_all(api, m)
    return api.post(f"{B}/missions/{m['id']}/execute").json()


def sessions(api, mid):
    return api.get(f"{B}/browser/sessions?mission_id={mid}").json()["items"]


# ---------------------------------------------------------------- the signature mission: identity, version, effect
def test_signature_mission_two_jordans_latest_report_browser_actions_and_independent_verification(api):
    t = api.me["tenant_id"]
    m = api.post(f"{B}/missions", {"intent": FOLLOW}).json()
    labels = [c["label"] for c in m["clarification"]["candidates"]]
    assert sum("Jordan Lee" in x for x in labels) == 2 and any("C-104" in x for x in labels) and any("C-208" in x for x in labels)   # refuses to pick by name
    assert m["clarification"]["candidates"][0]["hint"] != m["clarification"]["candidates"][1]["hint"]
    m = api.post(f"{B}/missions/{m['id']}/bind", {"role": "contact_id", "value": next(c["id"] for c in m["clarification"]["candidates"] if "C-104" in c["label"])}).json()
    assert m["status"] == "NEEDS_APPROVAL" and m["bindings"]["report_id"] == "R-22"                  # latest Operations report (v4), not v3, not Sales
    a1, a2 = m["plan"]["actions"]
    assert (a1["kind"], a2["kind"]) == ("browser_crm_task", "browser_send_report") and a2["depends_on"] == [a1["id"]]
    assert a2["params"]["attachment_sha256"] and a2["params"]["to_addr"] == "jordan.lee@ops.example.test" and "SIMULATED" in a2["params"]["body"]
    assert any("SIMULATED" in n for n in m["plan"]["notes"])
    assert truth(t, "crm", "task_created") == [] and truth(t, "outbox", "message_committed") == []      # nothing happened before approval
    done = run(api, m)
    assert done["status"] == "VERIFIED"
    assert len(truth(t, "crm", "task_created")) == 1 and len(truth(t, "outbox", "message_committed")) == 1   # oracle: exactly one of each
    claims = {c["action_id"]: c for c in done["outcome"]["claims"]}
    assert "independent of the browser" in claims[a1["id"]]["evidence"]["scope"] and claims[a2["id"]]["evidence"]["delivery"].startswith("SIMULATED")
    ss = sessions(api, m["id"])
    assert len(ss) >= 3 and all(s["blocked_requests"] == [] for s in ss)                            # observer + 2 executor sessions, nothing escaped
    snaps = [x for s in ss for x in s["snapshots"]]
    assert {"observe", "before", "after"} <= {x["phase"] for x in snaps}
    after = next(x for x in snaps if x["phase"] == "after" and "crm" in x["label"])
    before = next(x for x in snaps if x["phase"] == "before" and "crm" in x["label"])
    assert after["dom_sha"] != before["dom_sha"] and len(after["screenshot_sha"]) == 64 and after["fused"]["api_sha"] and after["fused"]["elements"] > 10   # state fusion
    png = api.get(after["screenshot_url"].replace("/api/v1", B))
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_other_jordan_gets_the_sales_report(api):
    m = start(api, "C-208")
    assert m["bindings"]["report_id"] == "R-31" and m["plan"]["actions"][1]["params"]["to_addr"] == "jordan.lee@sales.example.test"
    assert run(api, m)["status"] == "VERIFIED"


def test_report_with_mismatched_bytes_is_refused(api):
    m = api.post(f"{B}/missions", {"intent": "Prepare a follow-up for Priya Nair using the latest report and send it"}).json()
    # Priya has no report in the store: honest empty result, not an invented attachment
    assert m["clarification"]["type"] == "no_candidates" and m["plan"] == {}


# ---------------------------------------------------------------- adversarial browser faults
def test_lost_acknowledgement_in_the_browser_is_reconciled_not_resent(api):
    t = api.me["tenant_id"]
    m = start(api)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "ack_loss"})
    done = run(api, m)
    assert done["status"] == "VERIFIED"
    types = [e["type"] for e in api.get(f"{B}/missions/{m['id']}/events").json()["items"]]
    assert "ACK_LOST" in types and "RECONCILED_FOUND" in types and types.count("DISPATCHING") == 2    # one per action; never re-dispatched
    assert len(truth(t, "outbox", "message_committed")) == 1                                         # oracle: the message exists exactly once


def test_misleading_success_toast_is_caught_by_independent_verification_and_blocks_dependents(api):
    t = api.me["tenant_id"]
    m = start(api)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "silent_drop"})                              # CRM says "Task created" and writes nothing
    done = run(api, m)
    by = {a["kind"]: a["status"] for a in done["plan"]["actions"]}
    assert by == {"browser_crm_task": "FAILED", "browser_send_report": "SKIPPED_DEPENDENCY"}
    assert done["status"] == "FAILED" and done["escalated"] is True
    assert truth(t, "crm", "task_created") == [] and truth(t, "outbox", "message_committed") == []   # the toast lied; no report was sent on a false premise
    assert any("UI may have reported success" in c["evidence"]["reason"] for c in done["outcome"]["claims"])


def test_report_edited_after_approval_voids_the_approval_and_nothing_stale_is_sent(api):
    t = api.me["tenant_id"]
    m = start(api)
    old_sha = m["plan"]["actions"][1]["params"]["attachment_sha256"]
    approve_all(api, m)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "report_edited"})
    mid = api.post(f"{B}/missions/{m['id']}/execute").json()
    types = [e["type"] for e in api.get(f"{B}/missions/{m['id']}/events").json()["items"]]
    assert mid["status"] == "NEEDS_APPROVAL" and "APPROVAL_STALE_AT_DISPATCH" in types                 # temporal guard fired before the send
    assert len(truth(t, "crm", "task_created")) == 1 and truth(t, "outbox", "message_committed") == []  # CRM step kept; the send never happened
    r = approve_all(api, mid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_stale"                      # old digest cannot be reused
    fresh = api.get(f"{B}/missions/{m['id']}").json()
    new_sha = next(a for a in fresh["plan"]["actions"] if a["kind"] == "browser_send_report")["params"]["attachment_sha256"]
    assert fresh["revision"] == 2 and new_sha != old_sha and [a["kind"] for a in fresh["plan"]["actions"]] == ["browser_send_report"]   # completed CRM work preserved
    approve_all(api, fresh)
    final = api.post(f"{B}/missions/{m['id']}/execute").json()
    assert final["status"] == "VERIFIED"
    msgs = [x[0] for x in truth(t, "outbox", "message_committed")]
    assert len(msgs) == 1 and new_sha in msgs[0] and old_sha not in msgs[0]                            # the edited file was sent, once


def test_contact_record_changed_before_approval_forces_a_fresh_plan(api):
    m = start(api)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "contact_changed"})
    r = approve_all(api, m)
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_stale"
    cur = api.get(f"{B}/missions/{m['id']}").json()
    assert cur["revision"] == 2 and cur["plan"]["actions"][1]["params"]["to_addr"] == "new.address@moved.example.test"


def test_user_only_step_pauses_the_mission_and_never_types_credentials(api):
    t = api.me["tenant_id"]
    m = start(api)
    approve_all(api, m)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "login_wall"})
    r = api.post(f"{B}/missions/{m['id']}/execute").json()
    assert r["status"] == "AUTHORIZED" and r["paused"] is True
    ev = [e for e in api.get(f"{B}/missions/{m['id']}/events").json()["items"] if e["type"] == "USER_ACTION_REQUIRED"][0]
    assert ev["data"]["reason"] == "login" and "never enters passwords" in ev["data"]["note"]
    assert truth(t, "crm", "task_created") == []
    last = sessions(api, m["id"])[0]
    assert last["status"] == "USER_ACTION_REQUIRED" and last["user_action"]["reason"] == "login"
    assert api.post(f"{B}/missions/{m['id']}/execute").json()["error"]["code"] == "mission_paused"
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "login_cleared"})                            # the user signed in themselves
    api.post(f"{B}/missions/{m['id']}/resume")
    assert api.post(f"{B}/missions/{m['id']}/execute").json()["status"] == "VERIFIED"
    assert len(truth(t, "crm", "task_created")) == 1 and len(truth(t, "outbox", "message_committed")) == 1


def test_unexpected_modal_and_renamed_form_labels_are_handled_and_recorded(api):
    t = api.me["tenant_id"]
    m = start(api)
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "popup"})
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "layout_shift"})                             # label + button renamed by a simulated app update
    assert run(api, m)["status"] == "VERIFIED"
    notes = " | ".join(s["note"] or "" for s in sessions(api, m["id"]))
    assert "dismissed an unexpected modal" in notes and "used 'Follow-up title'" in notes and "used 'Save follow-up'" in notes
    assert len(truth(t, "crm", "task_created")) == 1


def test_request_allowlist_blocks_every_non_fixture_origin(api, db):
    t = api.me["tenant_id"]
    with rb.BrowserRun(db, t, rb.world_for(t)) as br:
        page = br.page()
        with pytest.raises(Exception):
            page.goto("http://example.com/")
        with pytest.raises(Exception):
            page.goto("http://169.254.169.254/latest/meta-data/")
    assert any("example.com" in u for u in br.blocked) and any("169.254.169.254" in u for u in br.blocked)
    assert sessions_for(db, t)[0].blocked_requests


def sessions_for(db, t):
    from sqlalchemy import select
    from app.models import BrowserSessionRow
    return list(db.scalars(select(BrowserSessionRow).where(BrowserSessionRow.tenant_id == t).order_by(BrowserSessionRow.started_at.desc())))


def test_browser_worlds_and_snapshots_are_tenant_isolated(api, api2):
    ma = start(api)
    run(api, ma)
    mb = start(api2)
    assert api.me["tenant_id"] != api2.me["tenant_id"]
    ta, tb = api.me["tenant_id"], api2.me["tenant_id"]
    assert rb.world_for(ta).crm.url != rb.world_for(tb).crm.url
    assert len(truth(ta, "crm", "task_created")) == 1 and truth(tb, "crm", "task_created") == []      # A's actions did not touch B's world
    snap = next(x for s in sessions(api, ma["id"]) for x in s["snapshots"])
    assert api2.get(snap["screenshot_url"].replace("/api/v1", B)).status_code == 404
    assert api2.get(f"{B}/browser/sessions?mission_id={ma['id']}").json()["items"] == []
    assert api2.get(f"{B}/missions/{ma['id']}/tasks").status_code == 404
    assert mb["status"] == "NEEDS_APPROVAL"


def test_browser_faults_are_refused_for_other_scenarios_and_status_is_honest(api):
    m = api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled refund"}).json()
    assert api.post(f"{B}/missions/{m['id']}/faults", {"kind": "login_wall"}).status_code == 409
    st = api.get(f"{B}/browser/status").json()
    assert st["cloud_browser"] == "BLOCKED" and st["fixture_browser"] == "AVAILABLE" and "Not a production isolation" in st["isolation"]


def test_revoking_the_browser_connector_stops_browser_actions(api):
    t = api.me["tenant_id"]
    m = start(api)
    approve_all(api, m)
    api.post(f"{B}/connectors/browser_fixture/revoke")
    done = api.post(f"{B}/missions/{m['id']}/execute").json()
    assert {a["kind"]: a["status"] for a in done["plan"]["actions"]} == {"browser_crm_task": "BLOCKED", "browser_send_report": "SKIPPED_DEPENDENCY"}
    assert truth(t, "crm", "task_created") == [] and truth(t, "outbox", "message_committed") == []


# ---------------------------------------------------------------- task DAG (typed, owned, persisted)
def test_every_mission_has_a_persisted_typed_task_dag_that_tracks_real_execution(api):
    m = api.post(f"{B}/missions", {"intent": "My flight FA2041 was cancelled. I need my refund, my hotel rescheduled, my calendar corrected, and please inform my family."}).json()
    tasks = m["tasks"]
    kinds = {t["kind"] for t in tasks}
    assert {"route_domains", "resolve_entities", "evaluate_risk", "gather_evidence", "read:alternatives", "read:policy", "read:calendar", "browser_crm_task"} - kinds == {"browser_crm_task"}
    by_id = {t["id"]: t for t in tasks}
    assert all(d in by_id for t in tasks for d in t["depends_on"])                                   # a real DAG: every edge resolves
    owners = {t["owner"] for t in tasks}
    assert {"domain_router", "entity_resolver", "policy", "evidence", "executor", "verifier", "specialist", "observer"} <= owners
    writes = [t for t in tasks if t["mode"] == "write"]
    notify = next(t for t in writes if t["kind"] == "notify_contact")
    refund = next(t for t in writes if t["kind"] == "refund_request")
    assert refund["id"] in notify["depends_on"] and all(t["status"] == "QUEUED" for t in writes)
    assert all(t["status"] == "DONE" for t in tasks if t["kind"].startswith("read:")) and all(t["output"].get("concurrent") for t in tasks if t["kind"].startswith("read:"))
    approve_all(api, m)
    done = api.post(f"{B}/missions/{m['id']}/execute").json()
    after = {t["kind"]: t for t in done["tasks"]}
    assert all(after[k]["status"] == "DONE" for k in ("refund_request", "notify_contact", "verify:refund_request", "final_receipt"))
    assert after["refund_request"]["started_at"] and after["refund_request"]["finished_at"] and after["refund_request"]["attempts"] == 1


def test_task_statuses_reflect_skips_and_revisions(api):
    m = api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled, refund and inform my family"}).json()
    api.post(f"{B}/missions/{m['id']}/faults", {"kind": "silent_drop"})
    approve_all(api, m)
    done = api.post(f"{B}/missions/{m['id']}/execute").json()
    st = {t["kind"]: t["status"] for t in done["tasks"]}
    assert st["refund_request"] == "FAILED" and st["verify:refund_request"] == "FAILED" and st["notify_contact"] == "SKIPPED"
    m2 = api.post(f"{B}/missions", {"intent": "Flight FA2087 cancelled refund"}).json()
    api.post(f"{B}/missions/{m2['id']}/revise", {"intent": "Flight FA2041 cancelled refund please"})
    t2 = api.get(f"{B}/missions/{m2['id']}/tasks").json()["items"]
    assert {t["revision"] for t in t2} == {1, 2} and all(t["status"] == "CANCELLED" for t in t2 if t["revision"] == 1 and t["mode"] == "write")


def test_new_agent_roles_are_least_privilege():
    for r in ("domain_router", "entity_resolver", "policy", "evidence", "observer"):
        with pytest.raises(agents.AgentPermissionError):
            agents.require(r, "dispatch")
    agents.require("observer", "browser_observe")
    with pytest.raises(agents.AgentPermissionError):
        agents.require("evidence", "browser_observe")


# ---------------------------------------------------------------- spoken / typed control commands
@pytest.mark.parametrize("text,cmd", [("stop", "stop"), ("please pause for a moment", "pause"), ("resume", "resume"), ("actually use the other one", "change"), ("undo that", "undo"),
                                      ("why did you pick it", "explain"), ("what happened so far", "what_happened"), ("ruko", "stop"), ("kya hua", "what_happened"), ("रोको", "stop"),
                                      ("जारी रखो", "resume"), ("நிறுத்து", "stop"), ("ఎందుకు", "explain"), ("blah blah", "unknown")])
def test_command_interpretation_multilingual(text, cmd):
    assert utterance.interpret(text)["command"] == cmd


def test_commands_drive_real_mission_operations_and_report_truthfully(api):
    m = api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled. I need my refund and my hotel rescheduled."}).json()
    u = lambda text: api.post(f"{B}/missions/{m['id']}/utterance", {"text": text}).json()  # noqa: E731
    r = u("explain")
    assert r["command"] == "explain" and "Request refund" in r["message"] and "Policy:" in r["message"]
    assert u("pause")["mission"]["paused"] is True and u("resume")["mission"]["paused"] is False
    approve_all(api, m)
    r = u("undo")
    assert r["ok"] is True and r["mission"]["status"] == "NEEDS_APPROVAL" and "approval is withdrawn" in r["message"]
    assert api.post(f"{B}/missions/{m['id']}/execute").status_code == 409                          # undone approval cannot run
    r = u("actually the flight is FA2087")
    assert r["command"] == "change" and r["mission"]["revision"] >= 2 and "Earlier approvals are void" in r["message"]
    cur = api.get(f"{B}/missions/{m['id']}").json()
    approve_all(api, cur)
    api.post(f"{B}/missions/{m['id']}/execute")
    r = u("what happened")
    assert "independently verified an effect" in r["message"] and r["ok"] is True
    r = u("undo")
    assert r["ok"] is False and r["supported"] is False and "no verified reversal" in r["message"]   # honest: executed effects are not reversible here
    r = u("stop")
    assert r["ok"] is False and "already" in r["message"]
    assert u("hmm")["command"] == "unknown"


def test_stop_cancels_a_running_plan_and_voids_approvals(api):
    m = api.post(f"{B}/missions", {"intent": "Flight FA2041 cancelled refund"}).json()
    approve_all(api, m)
    r = api.post(f"{B}/missions/{m['id']}/utterance", {"text": "stop"}).json()
    assert r["ok"] is True and r["mission"]["status"] == "CANCELLED"
    assert api.post(f"{B}/missions/{m['id']}/execute").status_code == 409


def test_demo_scenario_d_browser_follow_up_is_repeatable_and_verified(api):
    for _ in range(2):
        r = api.post(f"{B}/demo/scenarios/d/run").json()
        assert r["status"] == "VERIFIED" and r["crm_tasks_created"] == 1 and r["messages_sent_simulated"] == 1   # reset between runs: exactly one of each
        assert "not a live provider" in r["environment"]
    assert "report_followup" in {w["id"] for w in api.get(f"{B}/workflows").json()["items"]}
    w = api.post(f"{B}/workflows/report_followup/start", {"inputs": {"name": "Jordan Lee"}}).json()
    assert w["mission"]["status"] == "DISCOVERING" and w["mission"]["clarification"]["type"] == "entity_ambiguous"
