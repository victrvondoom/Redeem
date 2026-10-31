import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Action, FxMessage, FxRequest, Mission
from app.orchestration import agents, engine
from app.voice import bolna
from conftest import approve_all

FULL = ("My flight FA2041 was cancelled. I need my refund, my hotel rescheduled, my calendar corrected, "
        "and please inform my family. Also find me an alternative.")


def events(api, mid, **kw):
    return api.get(f"/api/v1/missions/{mid}/events").json()["items"]


def start(api, text=FULL):
    return api.post("/api/v1/missions", {"intent": text}).json()


# ---------------------------------------------------------------- agents
def test_agent_capability_matrix_is_least_privilege():
    for role in ("planner", "specialist", "observer", "verifier", "recovery", "memory"):
        with pytest.raises(agents.AgentPermissionError):
            agents.require(role, "dispatch")  # only the executor may perform consequential dispatch
    agents.require("executor", "dispatch")
    with pytest.raises(agents.AgentPermissionError):
        agents.require("executor", "plan")
    with pytest.raises(agents.AgentPermissionError):
        agents.require("recovery", "dispatch")  # recovery may look up, never resend
    with pytest.raises(agents.AgentPermissionError):
        agents.require("ghost", "read_lookup")


def test_every_agent_makes_an_observable_contribution(api):
    m = start(api)
    approve_all(api, m)
    api.post(f"/api/v1/missions/{m['id']}/faults", {"kind": "ack_loss"})
    api.post(f"/api/v1/missions/{m['id']}/execute")
    who = {i["agent"].split(":")[0] for i in api.get(f"/api/v1/missions/{m['id']}/agents").json()["items"]}
    assert {"planner", "specialist", "memory", "executor", "verifier", "recovery"} <= who
    only = api.get(f"/api/v1/missions/{m['id']}/agents?agent=specialist").json()["items"]
    assert only and all(i["agent"].startswith("specialist") for i in only)


def test_executor_role_is_required_to_run(api, monkeypatch):
    m = start(api, "Flight FA2041 cancelled refund")
    approve_all(api, m)
    monkeypatch.setitem(agents.CAPABILITIES, "executor", frozenset())
    with pytest.raises(agents.AgentPermissionError):
        api.c.post(f"/api/v1/missions/{m['id']}/execute", headers=api._h())


# ---------------------------------------------------------------- task graph
def test_cross_domain_graph_with_dependency_family_message_and_parallel_reads(api, db):
    m = start(api)
    kinds = [a["kind"] for a in m["plan"]["actions"]]
    assert kinds == ["refund_request", "hotel_change_request", "calendar_update", "notify_contact"]
    refund, notify = m["plan"]["actions"][0], m["plan"]["actions"][3]
    assert notify["depends_on"] == [refund["id"]] and m["plan"]["actions"][1]["depends_on"] == []
    assert m["plan"]["graph"][3]["depends_on"] == [refund["id"]]
    alts = m["plan"]["reads"]["alternatives"]
    assert any(a["bookable"] for a in alts) and any(not a["bookable"] for a in alts)  # sold-out option shown honestly
    rc = [e for e in events(api, m["id"]) if e["type"] == "READS_COMPLETED"][0]["data"]
    assert rc["concurrent"] is True and set(rc["tasks"]) == {"alternatives", "policy", "calendar"}
    approve_all(api, m)
    done = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    assert done["status"] == "VERIFIED" and len(done["outcome"]["verified"]) == 4
    db.expire_all()
    msg = db.scalar(select(FxMessage).where(FxMessage.tenant_id == api.me["tenant_id"]))
    assert msg.status == "DRAFTED" and "NOT sent" in done["outcome"]["claims"][-1]["evidence"]["scope"]


def test_dependent_task_is_skipped_when_its_dependency_fails_verification(api, db):
    m = start(api)
    api.post(f"/api/v1/missions/{m['id']}/faults", {"kind": "silent_drop"})
    approve_all(api, m)
    done = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    by = {a["kind"]: a["status"] for a in done["plan"]["actions"]}
    assert by["refund_request"] == "FAILED" and by["notify_contact"] == "SKIPPED_DEPENDENCY"
    assert by["hotel_change_request"] == by["calendar_update"] == "VERIFIED"
    assert done["status"] == "PARTIALLY_VERIFIED"  # never a generic success
    db.expire_all()
    assert db.scalar(select(FxMessage)) is None  # no message claiming a refund that never happened
    assert any(e["type"] == "SKIPPED_DEPENDENCY" for e in events(api, m["id"]))


def test_correction_mid_execution_preserves_completed_work(api, db):
    m = start(api, "Flight FA2041 cancelled. I need my refund and my hotel rescheduled.")
    approve_all(api, m)
    mission = db.get(Mission, m["id"])

    def interrupt(action):
        if action.kind == "hotel_change_request":
            engine.revise(db, mission, intent=mission.intent + " Actually, don't cancel the hotel, just change the date.", reason="user_correction")
            db.commit()

    engine.execute(db, mission, before_dispatch=interrupt)
    db.expire_all()
    mine = lambda kind: list(db.scalars(select(FxRequest).where(FxRequest.tenant_id == api.me["tenant_id"], FxRequest.kind == kind)))  # noqa: E731
    assert len(mine("refund_request")) == 1 and mine("hotel_change_request") == []   # refund preserved; stale hotel never ran
    cur = api.get(f"/api/v1/missions/{m['id']}").json()
    assert cur["revision"] == 2 and cur["status"] == "NEEDS_APPROVAL"
    assert [a["kind"] for a in cur["plan"]["actions"]] == ["hotel_change_request"]   # refund not re-planned
    assert any("already exists" in n for n in cur["plan"]["notes"])
    old = db.scalars(select(Action).where(Action.mission_id == m["id"], Action.revision == 1)).all()
    assert {a.kind: a.status for a in old} == {"refund_request": "VERIFIED", "hotel_change_request": "SUPERSEDED"}
    approve_all(api, cur)
    assert api.post(f"/api/v1/missions/{m['id']}/execute").json()["status"] == "VERIFIED"
    db.expire_all()
    assert len(mine("refund_request")) == 1 and len(mine("hotel_change_request")) == 1


# ---------------------------------------------------------------- mission control
def test_pause_resume_blocks_and_continues_without_repeating(api, db):
    m = start(api, "Flight FA2041 cancelled. I need my refund and my hotel rescheduled.")
    approve_all(api, m)
    assert api.post(f"/api/v1/missions/{m['id']}/pause").json()["paused"] is True
    r = api.post(f"/api/v1/missions/{m['id']}/execute")
    assert r.status_code == 409 and r.json()["error"]["code"] == "mission_paused"
    api.post(f"/api/v1/missions/{m['id']}/resume")
    mission = db.get(Mission, m["id"])

    def pause_before_hotel(action):
        if action.kind == "hotel_change_request":
            engine.pause(db, mission); db.commit()

    engine.execute(db, mission, before_dispatch=pause_before_hotel)
    cur = api.get(f"/api/v1/missions/{m['id']}").json()
    assert cur["status"] == "AUTHORIZED" and {a["kind"]: a["status"] for a in cur["plan"]["actions"]} == {"refund_request": "VERIFIED", "hotel_change_request": "AUTHORIZED"}
    api.post(f"/api/v1/missions/{m['id']}/resume")
    assert api.post(f"/api/v1/missions/{m['id']}/execute").json()["status"] == "VERIFIED"
    db.expire_all()
    assert db.query(FxRequest).filter(FxRequest.tenant_id == api.me["tenant_id"], FxRequest.kind == "refund_request").count() == 1


def test_reject_one_then_all(api):
    m = start(api, "Flight FA2041 cancelled. I need my refund and my hotel rescheduled.")
    hotel = m["plan"]["actions"][1]
    r = api.post(f"/api/v1/missions/{m['id']}/reject", {"action_ids": [hotel["id"]], "reason": "keep hotel"}).json()
    assert r["status"] == "NEEDS_APPROVAL"
    assert api.post(f"/api/v1/missions/{m['id']}/reject", {"action_ids": [hotel["id"]]}).status_code == 404  # already rejected
    r = api.post(f"/api/v1/missions/{m['id']}/reject", {"action_ids": [m["plan"]["actions"][0]["id"]]}).json()
    assert r["status"] == "CANCELLED"


def test_observer_escalates_on_contradictory_evidence(api):
    m = start(api, "Flight FA2041 cancelled refund")
    api.post(f"/api/v1/missions/{m['id']}/faults", {"kind": "silent_drop"})
    approve_all(api, m)
    done = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    assert done["escalated"] is True
    types = [e["type"] for e in events(api, m["id"])]
    assert "HUMAN_ESCALATION" in types
    assert any(i["kind"] == "contradictory_evidence" for i in api.get(f"/api/v1/missions/{m['id']}/agents?agent=observer").json()["items"])


def test_manual_escalation_is_recorded_and_not_simulated_as_handoff(api):
    m = start(api, "Flight FA2041 cancelled refund")
    api.post(f"/api/v1/missions/{m['id']}/escalate")
    e = [x for x in events(api, m["id"]) if x["type"] == "HUMAN_ESCALATION"][0]
    assert "no external handoff" in e["data"]["note"]


# ---------------------------------------------------------------- evidence center
def test_evidence_center_categories_hashes_and_reports(api):
    m = start(api, "Flight FA2041 cancelled refund")
    approve_all(api, m)
    api.post(f"/api/v1/missions/{m['id']}/execute")
    ev = api.get(f"/api/v1/missions/{m['id']}/evidence").json()["items"]
    cats = {e["category"] for e in ev}
    assert {"USER_PROVIDED", "INFERRED", "PROVIDER_CONFIRMED", "DATABASE_VERIFIED"} <= cats
    assert all(len(e["content_hash"]) == 64 and e["id"].startswith("evd_") and e["retention"]["deletable"] and e["mission_id"] == m["id"] for e in ev)
    ack = [e for e in ev if e["category"] == "PROVIDER_CONFIRMED"][0]
    assert ack["verification_status"] == "ACK_ONLY_NOT_PROOF"   # an acknowledgement is never presented as proof
    assert all(e["verification_status"] == "VERIFIED" for e in ev if e["category"] == "DATABASE_VERIFIED")
    assert api.get(f"/api/v1/missions/{m['id']}/evidence?category=INFERRED").json()["items"]
    rj = api.get(f"/api/v1/missions/{m['id']}/report").json()
    assert rj["evidence_counts"]["DATABASE_VERIFIED"] >= 1 and rj["outcome"]["status"] == "VERIFIED"
    md = api.get(f"/api/v1/missions/{m['id']}/report?format=md")
    assert md.headers["content-type"].startswith("text/markdown") and "DATABASE_VERIFIED" in md.text and "attachment" in md.headers["content-disposition"]
    # stable ids: same evidence, same id
    assert [e["id"] for e in ev] == [e["id"] for e in api.get(f"/api/v1/missions/{m['id']}/evidence").json()["items"]]


def test_unverified_failures_appear_as_unverified_evidence(api):
    m = start(api, "Flight FA2041 cancelled refund")
    api.post(f"/api/v1/missions/{m['id']}/faults", {"kind": "silent_drop"})
    approve_all(api, m)
    api.post(f"/api/v1/missions/{m['id']}/execute")
    ev = api.get(f"/api/v1/missions/{m['id']}/evidence").json()
    assert any(e["category"] == "UNVERIFIED" and e["verification_status"] == "FAILED" for e in ev["items"])
    assert ev["remaining_uncertainty"]


# ---------------------------------------------------------------- connectors
def test_connector_manifests_and_health_never_overclaim(api):
    mf = {m["provider"]: m for m in api.get("/api/v1/connectors/manifests").json()["items"]}
    assert mf["booking_fixture"]["condition"] == "FIXTURE_VERIFIED" and mf["bolna"]["condition"] == "UNCONFIGURED"
    assert all(m["condition"] != "LIVE_VERIFIED" for m in mf.values())
    assert all({"scopes", "capabilities", "retry", "idempotency", "verification", "revocable"} <= set(m) for m in mf.values())
    h = {x["provider"]: x for x in api.get("/api/v1/connectors/health").json()["items"]}
    assert h["booking_fixture"]["healthy"] is True and h["bolna"]["configured"] is False and h["google_calendar"]["condition"] == "UNCONFIGURED"
    api.post("/api/v1/connectors/booking_fixture/revoke")
    h = {x["provider"]: x for x in api.get("/api/v1/connectors/health").json()["items"]}
    assert h["booking_fixture"]["healthy"] is False and h["booking_fixture"]["detail"] == "revoked"


# ---------------------------------------------------------------- demo scenarios
def test_demo_scenario_a_consumer_super_agent_is_repeatable(api, db):
    for _ in range(2):
        r = api.post("/api/v1/demo/scenarios/a/run").json()
        assert r["status"] == "VERIFIED" and "not a live provider" in r["environment"]
        m = api.get(f"/api/v1/missions/{r['mission_id']}").json()
        assert [a["kind"] for a in m["plan"]["actions"]] == ["refund_request", "hotel_change_request", "calendar_update", "notify_contact"]
        assert any(e["type"] == "DEMO_AUTO_APPROVAL" for e in events(api, r["mission_id"]))
        assert m["plan"]["reads"]["alternatives"]


def test_demo_scenario_b_business_operator(api, db):
    r = api.post("/api/v1/demo/scenarios/b/run").json()
    assert r["status"] == "VERIFIED"
    m = api.get(f"/api/v1/missions/{r['mission_id']}").json()
    assert m["plan"]["actions"][0]["params"]["qty"] == 2 and m["plan"]["actions"][0]["params"]["customer_name"] == "Amit Patel"
    assert m["outcome"]["claims"][0]["evidence"]["stock_before"] == 4 and m["outcome"]["claims"][0]["evidence"]["stock_now"] == 2


def test_demo_scenario_c_adversarial_recovery(api):
    r = api.post("/api/v1/demo/scenarios/c/run").json()
    assert r["status"] == "VERIFIED" and r["revision"] == 2
    assert r["stale_approval_replay_blocked"] is True
    assert r["refund_requests_on_intended_booking"] == 1 and r["refund_requests_on_wrong_booking"] == 0
    types = [e["type"] for e in events(api, r["mission_id"])]
    assert {"APPROVAL_INVALIDATED", "ACK_LOST", "RECONCILED_FOUND", "FAULT_ARMED"} <= set(types) and types.count("DISPATCHING") == 1
    assert api.post("/api/v1/demo/scenarios/z/run").status_code == 404


def test_demo_reset_restores_fixtures_but_keeps_missions(api, db):
    api.post("/api/v1/demo/scenarios/b/run")
    assert api.post("/api/v1/demo/reset").json()["reset"] is True
    assert api.get("/api/v1/missions").json()["total"] == 1
    r = api.post("/api/v1/demo/scenarios/b/run").json()
    assert r["status"] == "VERIFIED"


# ---------------------------------------------------------------- analytics
def test_analytics_funnel_comes_from_real_events(api):
    f0 = api.get("/api/v1/analytics/funnel").json()
    assert f0["signup_at"] and f0["first_mission_at"] is None and f0["missions_started"] == 0
    m = start(api, "Flight FA2041 cancelled refund")
    approve_all(api, m); api.post(f"/api/v1/missions/{m['id']}/execute")
    f = api.get("/api/v1/analytics/funnel").json()
    assert f["missions_started"] == 1 and f["approvals"] == 1 and f["verified"] == 1 and f["first_verified_outcome_at"] and f["abandoned"] == 0
    assert "no benchmarks" in f["scope"]


# ---------------------------------------------------------------- voice continuity & provider hardening
def configure(handler, secret="whsec-test"):
    settings.bolna_api_key, settings.bolna_agent_id, settings.bolna_webhook_secret = "bn-test-KEY", "agent-1", secret
    bolna.make_client = lambda: bolna.BolnaClient("https://api.bolna.test", "bn-test-KEY", "agent-1", 2.0, transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def restore():
    orig = bolna.make_client
    bolna.BREAKER.failures, bolna.BREAKER.opened_at = 0, None
    yield
    bolna.make_client = orig
    settings.bolna_webhook_allowed_ips = ""


def voice_call(api):
    configure(lambda r: httpx.Response(200, json={"sip": 1}))
    api.post("/api/v1/voice/consent", {"purpose": "voice_call", "granted": True})
    cid = api.post("/api/v1/voice/session").headers["x-redeem-call-id"]
    api.post(f"/api/v1/voice/calls/{cid}/attach", {"execution_id": "exec-9"})
    return cid


def tool(api, name, args, token="whsec-test"):
    return api.c.post(f"/api/v1/voice/tools/{name}?token={token}", json={"execution_id": "exec-9", "args": args})


def test_voice_follow_ups_resolve_references_and_keep_mission_context(api):
    voice_call(api)
    r = tool(api, "start_mission", {"intent": "Flight cancelled, I need a refund"}).json()
    mid = r["mission_id"]
    assert r["status"] == "DISCOVERING"
    # follow-up in the SAME call: no mission id needed; "the second option" resolves against the open question
    cand = api.get(f"/api/v1/missions/{mid}").json()["clarification"]["candidates"]
    out = tool(api, "mission_reply", {"text": "the second option please"}).json()
    assert out["understood"] is True and out["status"] == "NEEDS_APPROVAL"
    assert api.get(f"/api/v1/missions/{mid}").json()["bindings"]["booking_id"] == cand[1]["id"]
    assert tool(api, "mission_reply", {"text": "hmm okay"}).json()["understood"] is False
    # correction by voice becomes a new revision and voids approvals
    out = tool(api, "mission_reply", {"text": "Actually it is flight FA2087"}).json()
    assert out["revision"] == 2 and out["status"] == "NEEDS_APPROVAL"


def test_voice_read_back_is_localised_and_cannot_approve(api, db):
    voice_call(api)
    api.patch("/api/v1/auth/language", {"language": "hi"})
    mid = tool(api, "start_mission", {"intent": "Flight FA2041 cancelled refund"}).json()["mission_id"]
    db.query(Mission).filter(Mission.id == mid).update({"language_selected": "hi"}); db.commit()
    rb = tool(api, "read_back_plan", {}).json()
    assert "₹8,450.00" in rb["spoken"] and "मंज़ूर" in rb["spoken"] and rb["can_approve_by_voice"] is False
    assert "Rahul Sharma" in rb["spoken"]  # the affected entity is named before any authorisation is requested
    assert tool(api, "approve", {}).status_code == 404
    assert api.get(f"/api/v1/missions/{mid}").json()["status"] == "NEEDS_APPROVAL"


def test_voice_interrupt_pauses_stale_execution(api):
    voice_call(api)
    mid = tool(api, "start_mission", {"intent": "Flight FA2041 cancelled refund"}).json()["mission_id"]
    approve_all(api, api.get(f"/api/v1/missions/{mid}").json())
    assert tool(api, "interrupt", {}).json()["paused"] is True
    assert api.post(f"/api/v1/missions/{mid}/execute").json()["error"]["code"] == "mission_paused"
    assert any(e["type"] == "VOICE_INTERRUPT" for e in events(api, mid))


def test_voice_tools_need_an_active_mission(api):
    voice_call(api)
    r = tool(api, "read_back_plan", {})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_active_mission"


def test_session_mint_falls_back_to_documented_endpoint_on_404(api):
    seen = []

    def handler(req):
        seen.append(req.url.path)
        return httpx.Response(404, json={}) if req.url.path.endswith("freeswitch-session") else httpx.Response(200, json={"sip": "ok"})

    configure(handler)
    api.post("/api/v1/voice/consent", {"purpose": "voice_call", "granted": True})
    r = api.post("/api/v1/voice/session")
    assert r.status_code == 200 and r.json() == {"sip": "ok"} and seen == ["/web-call/freeswitch-session", "/web-call/session"]


def test_circuit_breaker_opens_after_repeated_provider_failures_then_recovers(api):
    clock = {"t": 0.0}
    bolna.BREAKER.clock = lambda: clock["t"]
    state = {"ok": False}
    configure(lambda r: httpx.Response(200, json={"sip": 1}) if state["ok"] else httpx.Response(500))
    api.post("/api/v1/voice/consent", {"purpose": "voice_call", "granted": True})
    codes = [api.post("/api/v1/voice/session").json()["error"]["code"] for _ in range(4)]
    assert codes[:3] == ["provider_unavailable"] * 3 and codes[3] == "provider_circuit_open"
    clock["t"], state["ok"] = 31.0, True   # cooldown elapsed, provider healthy again
    assert api.post("/api/v1/voice/session").status_code == 200
    import time
    bolna.BREAKER.clock = time.monotonic


def test_webhook_source_ip_allowlist(api):
    voice_call(api)
    settings.bolna_webhook_allowed_ips = "203.0.113.7"
    r = api.c.post("/api/v1/webhooks/bolna?token=whsec-test", json={"id": "exec-9"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "source_not_allowed"
    settings.bolna_webhook_allowed_ips = "testclient"
    assert api.c.post("/api/v1/webhooks/bolna?token=whsec-test", json={"id": "exec-9"}).status_code == 202


# ---------------------------------------------------------------- red team
def test_replayed_approval_and_double_execute_are_refused(api, db):
    m = start(api, "Flight FA2041 cancelled refund")
    items = [{"action_id": a["id"], "digest": a["digest"]} for a in m["plan"]["actions"]]
    assert api.post(f"/api/v1/missions/{m['id']}/approve", {"approvals": items}).status_code == 200
    assert api.post(f"/api/v1/missions/{m['id']}/approve", {"approvals": items}).status_code == 409   # replay
    assert api.post(f"/api/v1/missions/{m['id']}/execute").json()["status"] == "VERIFIED"
    assert api.post(f"/api/v1/missions/{m['id']}/execute").status_code == 409
    db.expire_all()
    assert db.query(FxRequest).filter(FxRequest.tenant_id == api.me["tenant_id"], FxRequest.kind == "refund_request").count() == 1


def test_new_endpoints_are_tenant_isolated(api, api2):
    m = start(api, "Flight FA2041 cancelled refund")
    for method, path, body in [("get", "evidence", None), ("get", "report", None), ("get", "agents", None), ("post", "pause", {}), ("post", "resume", {}),
                               ("post", "escalate", {}), ("post", "reject", {"action_ids": [m["plan"]["actions"][0]["id"]]})]:
        r = getattr(api2, method)(f"/api/v1/missions/{m['id']}/{path}", *([body] if method == "post" else []))
        assert r.status_code == 404, path
    assert api2.get(f"/api/v1/missions/{m['id']}/report?format=md").status_code == 404
    api2.post("/api/v1/demo/scenarios/a/run")   # B's demo reset must not touch A's fixtures
    assert api.get(f"/api/v1/missions/{m['id']}").json()["status"] == "NEEDS_APPROVAL"


def test_upload_filename_cannot_traverse_paths(api):
    r = api.post("/api/v1/documents", files={"file": ("../../etc/passwd", b"x", "text/plain")})
    name = r.json()["filename"]
    assert r.status_code == 201 and "/" not in name and "\\" not in name


def test_no_secret_ever_appears_in_responses(api):
    configure(lambda r: httpx.Response(500))
    api.post("/api/v1/voice/consent", {"purpose": "voice_call", "granted": True})
    blobs = [api.get("/api/v1/voice/status").text, api.get("/api/v1/connectors").text, api.get("/api/v1/connectors/health").text,
             api.get("/api/v1/connectors/manifests").text, api.post("/api/v1/voice/session").text, api.get("/api/v1/auth/me").text]
    assert all("bn-test-KEY" not in b and "whsec-test" not in b for b in blobs)


def test_unauthorized_agent_cannot_cause_consequential_effect(api, db):
    """Planner/observer/memory paths never dispatch: running them leaves provider state untouched."""
    m = start(api, "Flight FA2041 cancelled refund")
    mission = db.get(Mission, m["id"])
    agents.recall(db, mission)
    agents.observe(db, mission, db.scalars(select(Action).where(Action.mission_id == m["id"])).first(), "ACKED")
    assert db.query(FxRequest).count() == 0
    with pytest.raises(agents.AgentPermissionError):
        agents.require("planner", "dispatch")


def test_exported_agent_tools_match_the_endpoints_and_accept_bolna_flat_bodies(api):
    from app.voice import agent_config
    cfg = agent_config.build("https://h.example", "S")
    names = {t["name"] for t in cfg["tools"]}
    assert names == {"start_mission", "mission_reply", "read_back_plan", "interrupt", "search_catalogue", "lookup_booking", "save_answer", "recall"}
    assert "approve" not in names and "approve" not in " ".join(names)      # no approval tool exists to give the agent
    assert all(t["url"].startswith("https://h.example/api/v1/voice/tools/") and "execution_id" in t["parameters"]["required"] for t in cfg["tools"])
    assert cfg["status"] == "UNVERIFIED_AGAINST_LIVE_BOLNA"
    voice_call(api)
    flat = api.c.post("/api/v1/voice/tools/search_catalogue?token=whsec-test", json={"execution_id": "exec-9", "query": "mouse"}).json()
    assert flat["results"] and flat["results"][0]["name"].startswith("Orbit")
