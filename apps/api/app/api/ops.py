from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from ..connectors.registry import manifests
from ..core.deps import Ctx, audit, current_ctx, err
from ..db import utcnow
from ..evidence import center
from ..models import AuditEvent, Connection, Mission
from ..orchestration import engine, utterance
from ..resolve import browser as rb
from ..models import BrowserSessionRow, BrowserSnapshot
from ..schemas import BenchRunIn, RejectIn, UtteranceIn
from .. import config as _cfg
from .. import demo

router = APIRouter(prefix="/api/v1", tags=["operations"])


def _get(ctx: Ctx, mission_id: str) -> Mission:
    m = ctx.db.scalar(select(Mission).where(Mission.id == mission_id, Mission.tenant_id == ctx.tenant_id))
    if not m:
        raise err(404, "not_found", "Mission not found")
    return m


def _run(ctx: Ctx, m: Mission, fn, *a, **kw):
    try:
        fn(ctx.db, m, *a, **kw)
    finally:
        ctx.db.commit()
    return engine.mission_view(ctx.db, m)


@router.post("/missions/{mission_id}/recheck")
def recheck(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    return _run(ctx, _get(ctx, mission_id), engine.recheck)


@router.post("/missions/{mission_id}/pause")
def pause(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    audit(ctx.db, ctx, "mission.pause", mission_id)
    return _run(ctx, _get(ctx, mission_id), engine.pause)


@router.post("/missions/{mission_id}/resume")
def resume(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    audit(ctx.db, ctx, "mission.resume", mission_id)
    return _run(ctx, _get(ctx, mission_id), engine.resume)


@router.post("/missions/{mission_id}/reject")
def reject(mission_id: str, body: RejectIn, ctx: Ctx = Depends(current_ctx)):
    audit(ctx.db, ctx, "mission.reject", mission_id)
    return _run(ctx, _get(ctx, mission_id), engine.reject, body.action_ids, body.reason)


@router.post("/missions/{mission_id}/escalate")
def escalate(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    audit(ctx.db, ctx, "mission.escalate", mission_id)
    return _run(ctx, _get(ctx, mission_id), engine.escalate, "requested by user")


@router.get("/missions/{mission_id}/evidence")
def evidence(mission_id: str, ctx: Ctx = Depends(current_ctx), category: str | None = None):
    items = center.build(ctx.db, _get(ctx, mission_id))
    if category:
        items = [i for i in items if i["category"] == category]
    return {"items": items, "remaining_uncertainty": center.remaining_uncertainty(ctx.db, _get(ctx, mission_id))}


@router.get("/missions/{mission_id}/report")
def report(mission_id: str, ctx: Ctx = Depends(current_ctx), format: str = Query("json", pattern="^(json|md)$")):
    r = center.report(ctx.db, _get(ctx, mission_id))
    if format == "md":
        return Response(center.to_markdown(r), media_type="text/markdown", headers={
            "Content-Disposition": f'attachment; filename="redeem-report-{mission_id}.md"', "X-Content-Type-Options": "nosniff"})
    return r


@router.get("/missions/{mission_id}/agents")
def agent_activity(mission_id: str, ctx: Ctx = Depends(current_ctx), agent: str | None = None):
    from ..models import ActionEvent
    m = _get(ctx, mission_id)
    rows = ctx.db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id, ActionEvent.type == "AGENT").order_by(ActionEvent.seq))
    items = [{"seq": e.seq, **e.data, "action_id": e.action_id, "at": e.created_at.isoformat()} for e in rows]
    return {"items": [i for i in items if not agent or str(i["agent"]).startswith(agent)]}


# ---------------------------------------------------------------- connectors
@router.get("/connectors/manifests")
def connector_manifests(ctx: Ctx = Depends(current_ctx)):
    return {"items": manifests()}


@router.get("/connectors/health")
def connector_health(ctx: Ctx = Depends(current_ctx)):
    from ..config import settings
    conns = {c.provider: c for c in ctx.db.scalars(select(Connection).where(Connection.tenant_id == ctx.tenant_id))}
    out = []
    for mf in manifests():
        p = mf["provider"]
        if mf["kind"] == "fixture":
            c = conns.get(p)
            ok = bool(c and c.status == "active")
            out.append({"provider": p, "condition": mf["condition"], "configured": True, "healthy": ok,
                        "detail": "active" if ok else (c.status if c else "missing")})
        elif p == "bolna":
            out.append({"provider": p, "condition": "UNCONFIGURED" if not settings.bolna_configured else "CONFIGURED_NOT_LIVE_VERIFIED",
                        "configured": settings.bolna_configured, "healthy": False,
                        "detail": "credentials absent" if not settings.bolna_configured else "credentials present; no live call recorded"})
        else:
            out.append({"provider": p, "condition": "UNCONFIGURED", "configured": False, "healthy": False, "detail": "not configured"})
    return {"items": out, "checked_at": utcnow().isoformat()}


# ---------------------------------------------------------------- demo environment
@router.post("/demo/scenarios/{scenario}/run", status_code=201)
def run_demo(scenario: str, ctx: Ctx = Depends(current_ctx)):
    if scenario not in ("a", "b", "c", "d"):
        raise err(404, "not_found", "Unknown scenario")
    audit(ctx.db, ctx, "demo.run", scenario)
    return demo.run(ctx.db, ctx, scenario) | {"environment": "demo fixtures (not a live provider)"}


@router.post("/demo/reset")
def reset_demo(ctx: Ctx = Depends(current_ctx)):
    audit(ctx.db, ctx, "demo.reset")
    demo.reset_fixtures(ctx.db, ctx.tenant_id)
    return {"reset": True, "note": "Fixture data re-seeded. Your missions are kept."}


# ---------------------------------------------------------------- analytics (real events only)
@router.get("/analytics/funnel")
def funnel(ctx: Ctx = Depends(current_ctx)):
    db, t = ctx.db, ctx.tenant_id

    def first(action):
        return db.scalar(select(func.min(AuditEvent.created_at)).where(AuditEvent.tenant_id == t, AuditEvent.action == action))

    def count(action):
        return db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == t, AuditEvent.action == action)) or 0

    missions = list(db.scalars(select(Mission).where(Mission.tenant_id == t)))
    cutoff = utcnow() - timedelta(hours=24)
    open_states = {"INTENT_CAPTURED", "CLASSIFIED", "DISCOVERING", "NEEDS_APPROVAL"}
    iso = lambda x: x.isoformat() if x else None  # noqa: E731
    return {
        "scope": "This workspace only. Counts come from recorded events; no benchmarks or external user numbers.",
        "signup_at": iso(first("auth.register")), "first_voice_interaction_at": iso(first("voice.session_minted")),
        "first_mission_at": iso(first("mission.create")), "first_approval_at": iso(first("mission.approve")),
        "first_verified_outcome_at": iso(min((m.updated_at for m in missions if m.status == "VERIFIED"), default=None)),
        "missions_started": len(missions), "approvals": count("mission.approve"),
        "verified": sum(m.status == "VERIFIED" for m in missions), "partially_verified": sum(m.status == "PARTIALLY_VERIFIED" for m in missions),
        "failed": sum(m.status == "FAILED" for m in missions),
        "abandoned": sum(1 for m in missions if m.status in open_states and m.updated_at < cutoff),
        "repeat_missions": max(0, len(missions) - 1),
    }


# ---------------------------------------------------------------- spoken/typed commands on a mission
@router.post("/missions/{mission_id}/utterance")
def mission_utterance(mission_id: str, body: UtteranceIn, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.utterance", mission_id)
    try:
        res = utterance.apply(ctx.db, m, body.text)
    except engine.EngineError as e:
        ctx.db.commit()
        return {"command": utterance.interpret(body.text)["command"], "ok": False, "message": e.message, "mission": engine.mission_view(ctx.db, m)}
    ctx.db.commit()
    return {**res, "mission": engine.mission_view(ctx.db, m)}


@router.get("/missions/{mission_id}/tasks")
def mission_tasks(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    from ..orchestration import taskgraph
    return {"items": taskgraph.view(ctx.db, _get(ctx, mission_id))}


# ---------------------------------------------------------------- browser sessions, snapshots, faults
BROWSER_FAULTS = ("popup", "layout_shift", "login_wall", "login_cleared", "report_edited", "contact_changed", "slow_page")


def arm_browser_fault(ctx: Ctx, m: Mission, kind: str) -> None:
    w = rb.world_for(ctx.tenant_id)
    if kind == "popup":
        rb.set_fault(w, "crm", "popup")
    elif kind == "layout_shift":
        rb.set_fault(w, "crm", "layout_shift")
    elif kind == "login_wall":
        rb.set_fault(w, "crm", "login_wall")
    elif kind == "login_cleared":
        w.crm.faults.pop("login_wall", None)
    elif kind == "slow_page":
        rb.set_fault(w, "crm", "delay_ms", 1500)
    elif kind == "report_edited":
        w.docs.edit(m.bindings.get("report_id") or "R-22")                     # the file changes after it was reviewed/approved
    elif kind == "contact_changed":
        import sqlite3
        with sqlite3.connect(str(w.crm.db_path), timeout=10) as db:
            db.execute("UPDATE contacts SET email = 'new.address@moved.example.test' WHERE id = ?", (m.bindings.get("contact_id") or "C-104",))


def _snap_json(x: BrowserSnapshot) -> dict:
    return {"id": x.id, "phase": x.phase, "label": x.label, "url": x.url, "title": x.title, "dom_sha": x.dom_sha, "aria_sha": x.aria_sha, "screenshot_sha": x.screenshot_sha, "fused": x.fused,
            "screenshot_url": f"/api/v1/browser/snapshots/{x.id}/screenshot", "created_at": x.created_at.isoformat()}


@router.get("/browser/sessions")
def browser_sessions(ctx: Ctx = Depends(current_ctx), mission_id: str | None = None, limit: int = Query(30, ge=1, le=100)):
    stmt = select(BrowserSessionRow).where(BrowserSessionRow.tenant_id == ctx.tenant_id)
    if mission_id:
        stmt = stmt.where(BrowserSessionRow.mission_id == mission_id)
    rows = list(ctx.db.scalars(stmt.order_by(BrowserSessionRow.started_at.desc()).limit(limit)))
    snaps = list(ctx.db.scalars(select(BrowserSnapshot).where(BrowserSnapshot.tenant_id == ctx.tenant_id, BrowserSnapshot.session_id.in_([r.id for r in rows] or [""])).order_by(BrowserSnapshot.created_at)))
    return {"items": [{"id": r.id, "mission_id": r.mission_id, "action_id": r.action_id, "status": r.status, "origins": r.origins, "blocked_requests": r.blocked_requests, "user_action": r.user_action, "note": r.note,
                       "started_at": r.started_at.isoformat(), "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                       "snapshots": [_snap_json(x) for x in snaps if x.session_id == r.id]} for r in rows]}


@router.get("/browser/snapshots/{snap_id}/screenshot")
def snapshot_png(snap_id: str, ctx: Ctx = Depends(current_ctx)):
    from pathlib import Path
    x = ctx.db.scalar(select(BrowserSnapshot).where(BrowserSnapshot.id == snap_id, BrowserSnapshot.tenant_id == ctx.tenant_id))
    if not x or not x.screenshot_path or not Path(x.screenshot_path).is_file():
        raise err(404, "not_found", "Snapshot not found")
    return Response(Path(x.screenshot_path).read_bytes(), media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"})


# ---------------------------------------------------------------- command center overview (real counts, real attention items)
@router.get("/overview")
def overview(ctx: Ctx = Depends(current_ctx)):
    from ..models import ActionEvent, Case, CaseEvent, Document
    db, t = ctx.db, ctx.tenant_id
    ms = list(db.scalars(select(Mission).where(Mission.tenant_id == t)))
    cs = list(db.scalars(select(Case).where(Case.tenant_id == t)))
    by_m: dict[str, int] = {}
    for m in ms:
        by_m[m.status] = by_m.get(m.status, 0) + 1
    by_c: dict[str, int] = {}
    for c in cs:
        by_c[c.status] = by_c.get(c.status, 0) + 1
    att = []
    for m in ms:
        if m.status == "NEEDS_APPROVAL":
            att.append({"kind": "approval", "title": "Approve the plan", "detail": (m.plan or {}).get("summary") or m.intent, "href": f"/app/missions/{m.id}", "at": m.updated_at.isoformat()})
        elif m.status == "DISCOVERING" and m.clarification:
            att.append({"kind": "question", "title": "A detail is needed", "detail": m.clarification.get("message", ""), "href": f"/app/missions/{m.id}", "at": m.updated_at.isoformat()})
        elif m.status == "UNCERTAIN":
            att.append({"kind": "uncertain", "title": "Outcome uncertain", "detail": m.intent, "href": f"/app/missions/{m.id}", "at": m.updated_at.isoformat()})
        if m.paused and m.status not in ("VERIFIED", "CANCELLED", "FAILED"):
            att.append({"kind": "paused", "title": "Mission paused", "detail": m.intent, "href": f"/app/missions/{m.id}", "at": m.updated_at.isoformat()})
        if m.escalated:
            att.append({"kind": "escalated", "title": "Needs a human", "detail": m.intent, "href": f"/app/missions/{m.id}", "at": m.updated_at.isoformat()})
    from ..reclaim import casework
    for c in cs:
        if c.status == "AWAITING_INFO":
            att.append({"kind": "case_info", "title": "Case needs facts", "detail": ", ".join(x["field"].replace("_", " ") for x in c.missing), "href": f"/app/cases/{c.id}", "at": c.updated_at.isoformat()})
        elif c.status == "AWAITING_APPROVAL":
            att.append({"kind": "case_approval", "title": "Review and approve the draft", "detail": c.title, "href": f"/app/cases/{c.id}", "at": c.updated_at.isoformat()})
        if casework.overdue(c):
            att.append({"kind": "overdue", "title": "Follow-up overdue", "detail": c.title, "href": f"/app/cases/{c.id}", "at": c.updated_at.isoformat()})
    att.sort(key=lambda x: x["at"], reverse=True)
    ev = list(db.scalars(select(ActionEvent).where(ActionEvent.tenant_id == t, ActionEvent.type.in_(["VERIFIED", "VERIFICATION_FAILED", "APPROVED", "ACK_LOST", "RECONCILED_FOUND", "RECEIPT", "USER_ACTION_REQUIRED",
                                                                                                        "APPROVAL_INVALIDATED", "HUMAN_ESCALATION", "REVISION_CREATED"])).order_by(ActionEvent.seq.desc()).limit(12)))
    cev = list(db.scalars(select(CaseEvent).where(CaseEvent.tenant_id == t, CaseEvent.type.in_(["CASE_CREATED", "DOCUMENT_ATTACHED", "DRAFT_EDITED", "APPROVAL_INVALIDATED", "PROVIDER_UPDATE"])).order_by(CaseEvent.seq.desc()).limit(8)))
    feed = [{"at": e.created_at.isoformat(), "source": "mission", "type": e.type, "mission_id": e.mission_id, "href": f"/app/missions/{e.mission_id}"} for e in ev] + \
           [{"at": e.created_at.isoformat(), "source": "case", "type": e.type, "case_id": e.case_id, "href": f"/app/cases/{e.case_id}"} for e in cev]
    feed.sort(key=lambda x: x["at"], reverse=True)
    n_docs = db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == t)) or 0
    n_snap = db.scalar(select(func.count()).select_from(BrowserSnapshot).where(BrowserSnapshot.tenant_id == t)) or 0
    open_m = [m for m in ms if m.status not in ("VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "CANCELLED", "SUPERSEDED")]
    return {"counts": {"missions_total": len(ms), "missions_active": len(open_m), "missions_by_status": by_m, "cases_total": len(cs), "cases_by_status": by_c, "documents": n_docs,
                       "browser_snapshots": n_snap, "verified_outcomes": by_m.get("VERIFIED", 0)},
            "attention": att[:12], "recent": feed[:14], "scope": "Counts come from this workspace's database; nothing here is a benchmark or external figure."}


# ---------------------------------------------------------------- quality lab: runnable deterministic benchmark (separate process, separate database)
_bench_lock = __import__("threading").Lock()


@router.post("/quality/runs", status_code=201)
def run_benchmark(body: BenchRunIn, ctx: Ctx = Depends(current_ctx)):
    import json as _json
    import subprocess
    import sys
    import time
    from pathlib import Path
    from ..core.security import limiter
    from ..models import BenchmarkRun
    limiter.check(f"bench:{ctx.user.id}", 4)
    if not _bench_lock.acquire(blocking=False):
        raise err(409, "benchmark_busy", "A benchmark is already running; wait for it to finish.")
    runner = Path(__file__).resolve().parents[4] / "evals" / "runners" / "benchmark.py"
    run = BenchmarkRun(tenant_id=ctx.tenant_id, seed=body.seed, trials_per_cell=body.n)
    ctx.db.add(run)
    ctx.db.commit()
    out = Path(_cfg.settings.data_dir) / "benchmarks" / ctx.tenant_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{run.id}.json"
    t0 = time.perf_counter()
    try:
        r = subprocess.run([sys.executable, str(runner), "--n", str(body.n), "--seed", str(body.seed), "--out", str(path)], capture_output=True, text=True, timeout=170,
                           env={k: v for k, v in __import__("os").environ.items() if not k.startswith(("BOLNA_", "REDEEM_DATABASE"))})
        if r.returncode != 0 or not path.exists():
            raise RuntimeError((r.stderr or r.stdout)[-300:])
        data = _json.loads(path.read_text())
        run.summary, run.raw_path, run.status = data["summary"], str(path), "DONE"
    except Exception as e:  # noqa: BLE001
        run.status, run.error = "FAILED", str(e)[:300]
    finally:
        run.duration_seconds = round(time.perf_counter() - t0, 2)
        ctx.db.commit()
        _bench_lock.release()
    audit(ctx.db, ctx, "quality.run", run.id)
    ctx.db.commit()
    return _run_json(run)


def _run_json(r) -> dict:
    return {"id": r.id, "seed": r.seed, "trials_per_cell": r.trials_per_cell, "status": r.status, "duration_seconds": r.duration_seconds, "error": r.error, "started_at": r.started_at.isoformat(),
            "summary": r.summary, "mode": "local stateful fixtures (this run executed in a separate process and database)"}


@router.get("/quality/runs")
def list_runs(ctx: Ctx = Depends(current_ctx)):
    from ..models import BenchmarkRun
    return {"items": [_run_json(r) for r in ctx.db.scalars(select(BenchmarkRun).where(BenchmarkRun.tenant_id == ctx.tenant_id).order_by(BenchmarkRun.started_at.desc()).limit(20))]}


@router.get("/quality/runs/{run_id}/raw")
def run_raw(run_id: str, ctx: Ctx = Depends(current_ctx)):
    from pathlib import Path
    from ..models import BenchmarkRun
    r = ctx.db.scalar(select(BenchmarkRun).where(BenchmarkRun.id == run_id, BenchmarkRun.tenant_id == ctx.tenant_id))
    if not r or not r.raw_path or not Path(r.raw_path).is_file():
        raise err(404, "not_found", "Run not found")
    return Response(Path(r.raw_path).read_bytes(), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'})
