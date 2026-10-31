"""Live Computer API: pairing, devices, cloud computers, sessions, control (pause / takeover / stop), tasks,
approvals, live frames and the bridge WebSocket."""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..core.deps import Ctx, audit, current_ctx, err
from ..core.security import hash_token, limiter
from ..db import get_db, utcnow
from ..models import ComputerAction, ComputerDevice, ComputerFrame, ComputerScenario, ComputerScenarioVersion, ComputerSession, ComputerTask, PairingCode
from ..computer import agent, cloud, hub, vision
from ..computer import scenarios as SC
from ..computer import protocol as P
from ..computer.pipeline import Refused, perform

router = APIRouter(prefix="/api/v1/computer", tags=["computer"])
ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LIVE = ("ACTIVE", "PAUSED", "USER_CONTROL")


def _code() -> str:
    c = "".join(secrets.choice(ALPHA) for _ in range(8))
    return f"{c[:4]}-{c[4:]}"


def _dev(ctx: Ctx, did: str) -> ComputerDevice:
    d = ctx.db.scalar(select(ComputerDevice).where(ComputerDevice.id == did, ComputerDevice.tenant_id == ctx.tenant_id))
    if not d:
        raise err(404, "not_found", "Computer not found")
    return d


def _sess(ctx: Ctx, sid: str) -> ComputerSession:
    s = ctx.db.scalar(select(ComputerSession).where(ComputerSession.id == sid, ComputerSession.tenant_id == ctx.tenant_id))
    if not s:
        raise err(404, "not_found", "Session not found")
    return s


def _dev_json(d: ComputerDevice) -> dict:
    return {"id": d.id, "name": d.name, "kind": d.kind, "platform": d.platform, "os_version": d.os_version, "status": d.status, "online": hub.online(d.id),
            "device_state": hub.device_state(d.id), "monitors": d.monitors, "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "token_rotated_at": d.token_rotated_at.isoformat(), "created_at": d.created_at.isoformat()}


def _frame_json(f: ComputerFrame | None) -> dict | None:
    if not f:
        return None
    return {"id": f.id, "url": f"/api/v1/computer/frames/{f.id}", "width": f.width, "height": f.height, "monitor": f.monitor, "origin_x": f.origin_x, "origin_y": f.origin_y,
            "sha256": f.sha256, "active_window": f.active_window, "cursor": f.cursor, "captured_at": f.captured_at.isoformat()}


def _act_json(a: ComputerAction) -> dict:
    return {"id": a.id, "task_id": a.task_id, "actor": a.actor, "action": a.action, "params": {k: v for k, v in a.params.items() if k != "text"} | ({"text_len": len(a.params["text"])} if "text" in a.params else {}),
            "reason": a.reason, "target": a.target, "risk": a.risk, "status": a.status, "error": a.error, "before_frame_id": a.before_frame_id,
            "after_frame_id": a.after_frame_id, "at": a.created_at.isoformat()}


def _task_json(t: ComputerTask) -> dict:
    return {"id": t.id, "session_id": t.session_id, "instruction": t.instruction, "source": t.source, "call_id": t.call_id, "intent": t.intent, "status": t.status,
            "step": t.step, "report": t.report, "pending_approval": t.pending_approval, "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat()}


# ------------------------------------------------------------------ capability status
@router.get("/status")
def status(ctx: Ctx = Depends(current_ctx)):
    ok, why = cloud.available()
    return {"cloud_computer": {"available": ok, "detail": why}, "vision_model": vision.status(), "perception": vision.perception_modes(),
            "live_view": "screen updates about once per second (captured frames), not a video stream", "actions": sorted(P.ACTIONS),
            "bridge_install": "pip install ./apps/bridge  then  python -m redeem_bridge pair --server <this server> --code <code>"}


# ------------------------------------------------------------------ pairing
class ClaimIn(BaseModel):
    code: str = Field(min_length=9, max_length=9)
    name: str = Field(default="computer", max_length=60)
    platform: str = Field(default="", max_length=20)
    os_version: str = Field(default="", max_length=100)
    bridge_version: str = Field(default="", max_length=20)


@router.post("/pairing-codes", status_code=201)
def new_code(ctx: Ctx = Depends(current_ctx)):
    code = _code()
    ctx.db.add(PairingCode(code_hash=hash_token(code), tenant_id=ctx.tenant_id, user_id=ctx.user.id, expires_at=utcnow() + timedelta(minutes=10)))
    audit(ctx.db, ctx, "computer.pairing_code", None)
    ctx.db.commit()
    return {"code": code, "expires_in_s": 600}


@router.post("/pair/claim", status_code=201)
def claim(body: ClaimIn, request: Request, db=Depends(get_db)):
    """Called by the bridge. The one-time code is the only credential; it is consumed here."""
    limiter.check(f"pair:{request.client.host if request.client else '-'}", 10)
    pc = db.get(PairingCode, hash_token(body.code.strip().upper()))
    exp = pc.expires_at.replace(tzinfo=utcnow().tzinfo) if pc and not pc.expires_at.tzinfo else (pc.expires_at if pc else None)
    if not pc or pc.used_at or exp < utcnow():
        raise err(400, "invalid_code", "This pairing code is invalid, expired or already used")
    token = secrets.token_urlsafe(32)
    d = ComputerDevice(tenant_id=pc.tenant_id, user_id=pc.user_id, name=body.name.strip() or "computer", platform=body.platform, os_version=body.os_version,
                       bridge_version=body.bridge_version, token_hash=hash_token(token))
    db.add(d)
    db.flush()
    pc.used_at, pc.device_id = utcnow(), d.id
    db.commit()
    return {"device_id": d.id, "device_token": token}


@router.get("/devices")
def devices(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(ComputerDevice).where(ComputerDevice.tenant_id == ctx.tenant_id, ComputerDevice.status == "PAIRED").order_by(ComputerDevice.created_at.desc()))
    return {"items": [_dev_json(d) for d in rows]}


def _end_sessions(ctx: Ctx, device_id: str, status: str = "ENDED"):
    for s in ctx.db.scalars(select(ComputerSession).where(ComputerSession.device_id == device_id, ComputerSession.tenant_id == ctx.tenant_id, ComputerSession.status.in_(LIVE))):
        s.status, s.ended_at, s.control_epoch = status, utcnow(), s.control_epoch + 1


@router.delete("/devices/{did}", status_code=204)
def revoke(did: str, ctx: Ctx = Depends(current_ctx)):
    d = _dev(ctx, did)
    d.status, d.revoked_at = "REVOKED", utcnow()
    _end_sessions(ctx, d.id)
    audit(ctx.db, ctx, "computer.revoke", d.id)
    ctx.db.commit()
    if hub.online(d.id):
        try:
            hub.call(d.id, "stop", {}, timeout=3)
        except Exception:
            pass
    hub.kick(d.id)
    cloud.stop(d.id)


# ------------------------------------------------------------------ sessions
class SessionIn(BaseModel):
    device_id: str = Field(min_length=3, max_length=40)


def _open_session(ctx: Ctx, d: ComputerDevice) -> ComputerSession:
    if not hub.online(d.id):
        raise err(409, "device_offline", "That computer is not connected. Start the REDEEM Computer Bridge on it.")
    _end_sessions(ctx, d.id)
    s = ComputerSession(tenant_id=ctx.tenant_id, user_id=ctx.user.id, device_id=d.id, mode=d.kind, expires_at=utcnow() + timedelta(hours=2))
    ctx.db.add(s)
    audit(ctx.db, ctx, "computer.session_start", d.id)
    ctx.db.commit()
    try:
        hub.call(d.id, "resume", {}, timeout=5)
        perform(ctx.db, s, "observe_screen", {}, reason="first look at the screen", actor="agent")
        hub.call(d.id, "start_recording", {}, timeout=5)
    except Refused as e:
        raise err(502, e.code, e.detail)
    return s


@router.post("/sessions", status_code=201)
def open_session(body: SessionIn, ctx: Ctx = Depends(current_ctx)):
    s = _open_session(ctx, _dev(ctx, body.device_id))
    return live(s.id, ctx)


@router.post("/cloud", status_code=201)
def new_cloud(request: Request, ctx: Ctx = Depends(current_ctx)):
    ok, why = cloud.available()
    if not ok:
        raise err(503, "cloud_unavailable", why)
    if ctx.db.scalar(select(ComputerDevice).where(ComputerDevice.tenant_id == ctx.tenant_id, ComputerDevice.kind == "cloud", ComputerDevice.status == "PAIRED")):
        raise err(409, "cloud_exists", "You already have a cloud computer. End it before starting another.")
    server = os.environ.get("REDEEM_PUBLIC_API_URL") or str(request.base_url)
    try:
        d = cloud.start(ctx.db, ctx.tenant_id, ctx.user.id, server)
    except RuntimeError as e:
        raise err(503, "cloud_failed", str(e)[:300])
    audit(ctx.db, ctx, "computer.cloud_start", d.id)
    s = _open_session(ctx, d)
    return live(s.id, ctx)


@router.get("/sessions/{sid}/live")
def live(sid: str, ctx: Ctx = Depends(current_ctx), since: str | None = Query(None, max_length=40)):
    s = _sess(ctx, sid)
    ctx.db.refresh(s)
    d = ctx.db.get(ComputerDevice, s.device_id)
    f = ctx.db.get(ComputerFrame, s.latest_frame_id) if s.latest_frame_id else None
    tasks = list(ctx.db.scalars(select(ComputerTask).where(ComputerTask.session_id == s.id, ComputerTask.tenant_id == ctx.tenant_id).order_by(ComputerTask.created_at.desc()).limit(10)))
    acts = list(ctx.db.scalars(select(ComputerAction).where(ComputerAction.session_id == s.id, ComputerAction.tenant_id == ctx.tenant_id).order_by(ComputerAction.created_at.desc()).limit(40)))
    return {"session": {"id": s.id, "mode": s.mode, "status": s.status, "control_epoch": s.control_epoch, "expires_at": s.expires_at.isoformat(), "created_at": s.created_at.isoformat()},
            "device": _dev_json(d) if d else None, "frame": _frame_json(f), "tasks": [_task_json(t) for t in tasks], "actions": [_act_json(a) for a in acts]}


@router.get("/sessions")
def sessions(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(ComputerSession).where(ComputerSession.tenant_id == ctx.tenant_id).order_by(ComputerSession.created_at.desc()).limit(20))
    return {"items": [{"id": s.id, "device_id": s.device_id, "mode": s.mode, "status": s.status, "created_at": s.created_at.isoformat()} for s in rows]}


class ControlIn(BaseModel):
    op: str = Field(pattern="^(pause|resume|takeover|release|stop|end)$")


def apply_control(db, s: ComputerSession, op: str) -> None:
    if s.status in ("STOPPED", "ENDED") and op != "end":
        raise err(409, "session_closed", f"Session is {s.status}")
    new = {"pause": "PAUSED", "resume": "ACTIVE", "takeover": "USER_CONTROL", "release": "ACTIVE", "stop": "STOPPED", "end": "ENDED"}[op]
    s.status, s.control_epoch = new, s.control_epoch + 1
    if new in ("STOPPED", "ENDED"):
        s.ended_at = utcnow()
    db.commit()  # persisted first: the agent loop checks this before every step
    dev_op = {"pause": "pause", "resume": "resume", "takeover": "request_takeover", "release": "resume", "stop": "stop", "end": "stop"}[op]
    if hub.online(s.device_id):
        try:
            hub.call(s.device_id, dev_op, {}, timeout=5)
        except Exception:
            pass


@router.post("/sessions/{sid}/control")
def control(sid: str, body: ControlIn, ctx: Ctx = Depends(current_ctx)):
    s = _sess(ctx, sid)
    apply_control(ctx.db, s, body.op)
    audit(ctx.db, ctx, f"computer.{body.op}", s.id)
    ctx.db.commit()
    d = ctx.db.get(ComputerDevice, s.device_id)
    if body.op == "end" and d and d.kind == "cloud":
        d.status = "REVOKED"
        ctx.db.commit()
        cloud.stop(d.id)
        hub.kick(d.id)
    return {"status": s.status, "control_epoch": s.control_epoch}


class InputIn(BaseModel):
    action: str = Field(max_length=40)
    params: dict = Field(default_factory=dict)


@router.post("/sessions/{sid}/input")
def user_input(sid: str, body: InputIn, ctx: Ctx = Depends(current_ctx)):
    """The person drives the same computer from the web view while they have control. Recorded with actor=user."""
    s = _sess(ctx, sid)
    if body.action not in P.INPUT - {"launch_application", "open_url"}:
        raise err(422, "invalid_action", "Only pointer and keyboard input is accepted here")
    try:
        row, res = perform(ctx.db, s, body.action, body.params, actor="user", reason="person at the web view")
    except Refused as e:
        raise err(409 if e.code in ("not_in_control", "session_closed") else 422 if e.code == "invalid_action" else 502, e.code, e.detail)
    return {"ok": res.get("ok"), "frame_id": res.get("frame_id"), "action_id": row.id}


# ------------------------------------------------------------------ tasks
class TaskIn(BaseModel):
    instruction: str = Field(min_length=3, max_length=1000)


def create_task(db, s: ComputerSession, instruction: str, source: str = "typed", call_id: str | None = None, *, scenario: ComputerScenario | None = None,
                intent: dict | None = None) -> ComputerTask:
    if s.status != "ACTIVE":
        raise err(409, "not_active", f"Session is {s.status}. Resume it (or hand control back) first.")
    running = db.scalar(select(ComputerTask).where(ComputerTask.session_id == s.id, ComputerTask.status.in_(["PLANNING", "RUNNING", "PAUSED", "USER_CONTROL"])))
    if running:
        raise err(409, "task_running", "Another task is still running on this computer")
    t = ComputerTask(tenant_id=s.tenant_id, session_id=s.id, instruction=instruction.strip(), source=source, call_id=call_id)
    if scenario:
        t.scenario_id, t.scenario_version, t.intent = scenario.id, scenario.version, intent or {}
    db.add(t)
    db.commit()
    agent.start(t.id)
    return t


@router.post("/sessions/{sid}/tasks", status_code=202)
def new_task(sid: str, body: TaskIn, ctx: Ctx = Depends(current_ctx)):
    s = _sess(ctx, sid)
    t = create_task(ctx.db, s, body.instruction)
    audit(ctx.db, ctx, "computer.task", t.id)
    ctx.db.commit()
    return _task_json(t)


def _task(ctx: Ctx, tid: str) -> ComputerTask:
    t = ctx.db.scalar(select(ComputerTask).where(ComputerTask.id == tid, ComputerTask.tenant_id == ctx.tenant_id))
    if not t:
        raise err(404, "not_found", "Task not found")
    ctx.db.refresh(t)
    return t


@router.get("/tasks/{tid}")
def get_task(tid: str, ctx: Ctx = Depends(current_ctx)):
    t = _task(ctx, tid)
    acts = ctx.db.scalars(select(ComputerAction).where(ComputerAction.task_id == t.id, ComputerAction.tenant_id == ctx.tenant_id).order_by(ComputerAction.created_at))
    return {**_task_json(t), "actions": [_act_json(a) for a in acts]}


class ApproveIn(BaseModel):
    digest: str = Field(min_length=64, max_length=64)


@router.post("/tasks/{tid}/approve")
def approve(tid: str, body: ApproveIn, ctx: Ctx = Depends(current_ctx)):
    t = _task(ctx, tid)
    pa = t.pending_approval or {}
    if t.status != "NEEDS_APPROVAL" or not secrets.compare_digest(pa.get("digest", ""), body.digest):
        raise err(409, "approval_mismatch", "Nothing is waiting for approval with that exact action")
    t.pending_approval = {**pa, "approved_digest": body.digest, "approved_at": utcnow().isoformat()}
    t.status = "RUNNING"
    audit(ctx.db, ctx, "computer.approve", t.id)
    ctx.db.commit()
    agent.start(t.id)  # the loop re-observes and re-plans; the approval only matches if the action is still identical
    return _task_json(t)


@router.post("/tasks/{tid}/reject")
def reject(tid: str, ctx: Ctx = Depends(current_ctx)):
    t = _task(ctx, tid)
    if t.status != "NEEDS_APPROVAL":
        raise err(409, "nothing_pending", "Nothing is waiting for approval")
    t.status, t.pending_approval = "STOPPED", {**(t.pending_approval or {}), "rejected": True}
    t.report = {**(t.report or {}), "summary": "You declined the action. Nothing was sent."}
    ctx.db.commit()
    return _task_json(t)


# ------------------------------------------------------------------ scenario catalog (database-backed)
def _scn(ctx: Ctx, key: str, *, own_only: bool = False) -> ComputerScenario:
    SC.seed(ctx.db)
    q = select(ComputerScenario).where(ComputerScenario.key == key)
    q = q.where(ComputerScenario.tenant_id == ctx.tenant_id) if own_only else q.where((ComputerScenario.tenant_id == ctx.tenant_id) | ComputerScenario.tenant_id.is_(None))
    sc = ctx.db.scalars(q.order_by(ComputerScenario.tenant_id.is_(None))).first()  # a workspace entry wins over a built-in with the same key
    if not sc:
        raise err(404, "not_found", "Scenario not found")
    return sc


def _need_admin(ctx: Ctx) -> None:
    if ctx.role not in ("owner", "admin"):
        raise err(403, "forbidden", "Only workspace owners and administrators can change scenario definitions")


def _scn_json(sc: ComputerScenario, runs: list[ComputerTask] | None = None, detail: bool = False) -> dict:
    ok, why = _runnable(sc)
    out = {"id": sc.id, "key": sc.key, "name": sc.name, "description": sc.description, "category": sc.category, "enabled": sc.enabled, "version": sc.version,
           "required_os": sc.required_os, "required_capabilities": sc.required_capabilities, "built_in": sc.tenant_id is None, "runnable": ok, "unavailable_reason": why,
           "parameter_schema": sc.parameter_schema, "last_run": SC.run_view(runs[0]) if runs else None, "run_count": len(runs or []),
           "created_by": sc.created_by, "created_at": sc.created_at.isoformat(), "updated_at": sc.updated_at.isoformat()}
    if detail:
        out |= {"steps": sc.steps, "expected_result": sc.expected_result, "verification": sc.verification, "approvals": sc.approvals, "executor": sc.executor}
    return out


def _runnable(sc: ComputerScenario) -> tuple[bool, str | None]:
    if not sc.executor:
        return False, "Describes agent behaviour; it is not a task you can start."
    if not agent.supports(sc.executor):
        return False, "The computer agent does not implement this scenario yet (see docs/STATIC_TODO.md)."
    return True, None


@router.get("/scenarios")
def list_scenarios(ctx: Ctx = Depends(current_ctx), q: str = Query("", max_length=80), category: str = Query("", max_length=40), os: str = Query("", max_length=16)):
    SC.seed(ctx.db)
    rows = list(ctx.db.scalars(select(ComputerScenario).where((ComputerScenario.tenant_id == ctx.tenant_id) | ComputerScenario.tenant_id.is_(None)).order_by(ComputerScenario.name)))
    shadow = {r.key for r in rows if r.tenant_id}
    rows = [r for r in rows if r.enabled or r.tenant_id == ctx.tenant_id]
    rows = [r for r in rows if not (r.tenant_id is None and r.key in shadow)]
    if q:
        rows = [r for r in rows if q.lower() in f"{r.name} {r.description} {r.key}".lower()]
    if category:
        rows = [r for r in rows if r.category == category]
    if os:
        rows = [r for r in rows if r.required_os in (os, "any")]
    runs = SC.last_runs(ctx.db, ctx.tenant_id, rows)
    return {"items": [_scn_json(r, runs[r.id]) for r in rows], "categories": sorted({r.category for r in rows}), "operating_systems": sorted({r.required_os for r in rows})}


class ScenarioIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="general", max_length=40)
    required_capabilities: list[str] = Field(default_factory=list, max_length=12)
    required_os: str = "any"
    parameter_schema: dict = Field(default_factory=lambda: {"type": "object"})
    steps: list[dict] = Field(default_factory=list, max_length=40)
    expected_result: str = Field(default="", max_length=1000)
    verification: list[str] = Field(default_factory=list, max_length=12)
    approvals: list[str] = Field(default_factory=list, max_length=12)
    executor: str | None = Field(default=None, max_length=40)
    reason: str = Field(default="", max_length=300)


def _validated(body: dict) -> dict:
    try:
        return SC.validate_definition(body)
    except SC.Invalid as e:
        raise err(422, "invalid_scenario", str(e))


@router.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, ctx: Ctx = Depends(current_ctx)):
    _need_admin(ctx)
    d = _validated(body.model_dump(exclude={"reason"}))
    if ctx.db.scalar(select(ComputerScenario).where(ComputerScenario.key == d["key"], (ComputerScenario.tenant_id == ctx.tenant_id) | ComputerScenario.tenant_id.is_(None))):
        raise err(409, "key_exists", "A scenario with that key already exists")
    sc = ComputerScenario(tenant_id=ctx.tenant_id, created_by=ctx.user.email, **d)
    ctx.db.add(sc)
    ctx.db.flush()
    SC.record_version(ctx.db, sc, ctx.user.email, body.reason or "created")
    audit(ctx.db, ctx, "computer.scenario_create", sc.id)
    ctx.db.commit()
    return _scn_json(sc, [], detail=True)


@router.get("/scenarios/{key}")
def get_scenario(key: str, ctx: Ctx = Depends(current_ctx)):
    SC.seed(ctx.db)
    sc = _scn(ctx, key)
    return _scn_json(sc, SC.last_runs(ctx.db, ctx.tenant_id, [sc])[sc.id], detail=True)


@router.put("/scenarios/{key}")
def edit_scenario(key: str, body: ScenarioIn, ctx: Ctx = Depends(current_ctx)):
    _need_admin(ctx)
    sc = _scn(ctx, key)
    if sc.tenant_id is None:
        raise err(403, "built_in", "Built-in scenarios cannot be edited. Create a workspace scenario with a new key instead.")
    if body.key != sc.key:
        raise err(422, "key_immutable", "The key of a scenario cannot change")
    d = _validated(body.model_dump(exclude={"reason"}))
    for k, v in d.items():
        setattr(sc, k, v)
    sc.version += 1
    SC.record_version(ctx.db, sc, ctx.user.email, body.reason or "edited")
    audit(ctx.db, ctx, "computer.scenario_edit", sc.id)
    ctx.db.commit()
    return _scn_json(sc, SC.last_runs(ctx.db, ctx.tenant_id, [sc])[sc.id], detail=True)


class EnabledIn(BaseModel):
    enabled: bool


@router.post("/scenarios/{key}/enabled")
def set_enabled(key: str, body: EnabledIn, ctx: Ctx = Depends(current_ctx)):
    _need_admin(ctx)
    sc = _scn(ctx, key)
    if sc.tenant_id is None:
        raise err(403, "built_in", "Built-in scenarios are managed by the platform")
    sc.enabled = body.enabled
    audit(ctx.db, ctx, "computer.scenario_enable" if body.enabled else "computer.scenario_disable", sc.id)
    ctx.db.commit()
    return _scn_json(sc, SC.last_runs(ctx.db, ctx.tenant_id, [sc])[sc.id])


@router.get("/scenarios/{key}/versions")
def scenario_versions(key: str, ctx: Ctx = Depends(current_ctx)):
    sc = _scn(ctx, key)
    rows = ctx.db.scalars(select(ComputerScenarioVersion).where(ComputerScenarioVersion.scenario_id == sc.id).order_by(ComputerScenarioVersion.version.desc()))
    return {"items": [{"version": v.version, "changed_by": v.changed_by, "reason": v.reason, "created_at": v.created_at.isoformat(), "snapshot": v.snapshot} for v in rows]}


@router.get("/scenarios/{key}/runs")
def scenario_runs(key: str, ctx: Ctx = Depends(current_ctx)):
    sc = _scn(ctx, key)
    runs = SC.last_runs(ctx.db, ctx.tenant_id, [sc])[sc.id]
    return {"items": [{**SC.run_view(t), "scenario_version": t.scenario_version, "instruction": t.instruction} for t in runs[:50]]}


class RunIn(BaseModel):
    session_id: str = Field(min_length=3, max_length=40)
    params: dict = Field(default_factory=dict)


@router.post("/scenarios/{key}/run", status_code=202)
def run_scenario(key: str, body: RunIn, ctx: Ctx = Depends(current_ctx)):
    """Starts a real task on the chosen computer session through the same agent loop as typed tasks."""
    sc = _scn(ctx, key)
    if not sc.enabled:
        raise err(409, "scenario_disabled", "This scenario is disabled")
    ok, why = _runnable(sc)
    if not ok:
        raise err(501, "not_implemented", why or "not runnable")
    s = _sess(ctx, body.session_id)
    d = ctx.db.get(ComputerDevice, s.device_id)
    if sc.required_os != "any" and d and d.platform != sc.required_os:
        raise err(409, "os_mismatch", f"This scenario needs a {sc.required_os} computer; this one reports {d.platform or 'unknown'}")
    try:
        params = SC.check_params(sc, body.params)
        intent = agent.intent_for(sc.executor, params, ctx.tenant_id, ctx.db)
    except SC.Invalid as e:
        raise err(422, "invalid_parameters", str(e))
    except agent.BadParams as e:
        raise err(422, "invalid_parameters", str(e))
    t = create_task(ctx.db, s, f"Scenario {sc.key} v{sc.version}", scenario=sc, intent=intent)
    audit(ctx.db, ctx, "computer.scenario_run", t.id)
    ctx.db.commit()
    return {**_task_json(t), "scenario": {"key": sc.key, "version": sc.version}}


# ------------------------------------------------------------------ frames + bridge socket
@router.get("/frames/{fid}")
def frame_png(fid: str, ctx: Ctx = Depends(current_ctx)):
    f = ctx.db.scalar(select(ComputerFrame).where(ComputerFrame.id == fid, ComputerFrame.tenant_id == ctx.tenant_id))
    if not f or not Path(f.path).is_file():
        raise err(404, "not_found", "Frame not found")
    return Response(Path(f.path).read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.websocket("/bridge/ws")
async def bridge_ws(ws: WebSocket):
    await hub.serve(ws)


# ------------------------------------------------------------------ vision (provider-backed; no fake model)
@router.get("/vision")
def vision_status(ctx: Ctx = Depends(current_ctx)):
    return {**vision.status(), "perception": vision.perception_modes()}


class ProposeIn(BaseModel):
    task: str = Field(min_length=3, max_length=500)


@router.post("/sessions/{sid}/vision/propose")
def vision_propose(sid: str, body: ProposeIn, ctx: Ctx = Depends(current_ctx)):
    """Ask the configured multimodal model to propose ONE next operation for the newest frame. It is validated and grounded, never executed here."""
    s = _sess(ctx, sid)
    if not vision.configured():
        raise err(503, "PROVIDER_NOT_CONFIGURED", vision.status()["detail"])
    f = ctx.db.get(ComputerFrame, s.latest_frame_id) if s.latest_frame_id else None
    if not f or f.tenant_id != ctx.tenant_id:
        raise err(409, "no_frame", "Observe the screen first")
    try:
        prop = vision.plan(f, body.task)
    except vision.ProviderError as e:
        raise err(502, "vision_provider_error", str(e))
    ctx.db.refresh(s)
    return {"frame_id": f.id, "proposal": prop.model_dump(), "grounding": vision.ground_proposal(f, s.latest_frame_id, prop), "executed": False}
