from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select

from ..connectors.registry import manifests
from ..core.deps import Ctx, audit, current_ctx, err
from ..db import utcnow
from ..evidence import center
from ..models import AuditEvent, Connection, Mission
from ..orchestration import engine
from ..schemas import RejectIn
from .. import demo, config as _cfg  # noqa: F401

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
    if scenario not in ("a", "b", "c"):
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
