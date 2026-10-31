import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..config import settings
from ..memory import service as service_memory
from ..core.deps import Ctx, audit, current_ctx, err
from ..core.security import limiter
from ..db import SessionLocal
from ..models import ActionEvent, Document, FxBooking, FxFault, Mission
from ..orchestration import engine
from ..orchestration.engine import TERMINAL
from ..schemas import ApproveIn, BindIn, FaultIn, MissionIn, ReviseIn

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


def _get(ctx: Ctx, mission_id: str) -> Mission:
    m = ctx.db.scalar(select(Mission).where(Mission.id == mission_id, Mission.tenant_id == ctx.tenant_id))
    if not m:  # identical response for "missing" and "someone else's": no existence oracle
        raise err(404, "not_found", "Mission not found")
    return m


def _run(ctx: Ctx, m: Mission, fn, *a, **kw):
    try:
        fn(ctx.db, m, *a, **kw)
    finally:
        ctx.db.commit()  # keep ledger entries written before any refusal
    return engine.mission_view(ctx.db, m)


@router.post("", status_code=201)
def create(body: MissionIn, ctx: Ctx = Depends(current_ctx)):
    limiter.check(f"mission:{ctx.user.id}", 30)
    m = Mission(tenant_id=ctx.tenant_id, workspace_id=ctx.workspace_id, user_id=ctx.user.id, intent=body.intent,
                language_selected=body.language, source=body.source)
    ctx.db.add(m)
    ctx.db.flush()
    if body.document_id:
        doc = ctx.db.scalar(select(Document).where(Document.id == body.document_id,
                                                   Document.tenant_id == ctx.tenant_id))
        if not doc:
            raise err(404, "not_found", "Document not found")
        refs = doc.extracted.get("booking_refs", [])
        hits = list(ctx.db.scalars(select(FxBooking).where(
            FxBooking.tenant_id == ctx.tenant_id, FxBooking.ref.in_(refs), FxBooking.kind == "flight")))
        if len(hits) == 1:
            m.bindings = {"booking_id": hits[0].id}
            engine.emit(ctx.db, m, "ENTITY_BOUND", {"role": "booking_id", "id": hits[0].id,
                                                    "via": f"document:{doc.id}@v{doc.version}",
                                                    "document_sha256": doc.sha256})
    audit(ctx.db, ctx, "mission.create", m.id)
    used = service_memory.relevant(ctx.db, ctx, body.intent)
    if used:  # only confirmed, relevant memory; values stay out of the ledger (ids and fields only)
        engine.emit(ctx.db, m, "MEMORY_USED", {"items": [{"id": u["id"], "field": u["field"], "source": u["source_kind"]} for u in used],
                                              "note": "Confirmed memory prefilled; no repeated questions needed for these fields."})
    try:
        engine.start_mission(ctx.db, m, body.transcript_confidence if body.source == "voice" else None)
    finally:
        ctx.db.commit()
    return engine.mission_view(ctx.db, m) | {"memory_used": used}


@router.get("")
def list_missions(ctx: Ctx = Depends(current_ctx), q: str | None = Query(None, max_length=100),
                  status: str | None = None, domain: str | None = None,
                  limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Mission).where(Mission.tenant_id == ctx.tenant_id)
    if q:
        stmt = stmt.where(Mission.intent.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Mission.status == status)
    rows = list(ctx.db.scalars(stmt.order_by(Mission.created_at.desc()).limit(500)))
    if domain:
        rows = [r for r in rows if domain in (r.domains or [])]
    page = rows[offset: offset + limit]
    return {"items": [{"id": r.id, "status": r.status, "intent": r.intent, "domains": r.domains,
                       "scenario": r.scenario, "language_detected": r.language_detected,
                       "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
                       "outcome_headline": (r.outcome or {}).get("headline")} for r in page],
            "total": len(rows), "limit": limit, "offset": offset}


@router.get("/{mission_id}")
def get_mission(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    return engine.mission_view(ctx.db, _get(ctx, mission_id))


@router.post("/{mission_id}/bind")
def bind(mission_id: str, body: BindIn, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.bind", m.id, {"role": body.role})
    return _run(ctx, m, engine.bind, body.role, body.value)


@router.post("/{mission_id}/revise")
def revise(mission_id: str, body: ReviseIn, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.revise", m.id)
    return _run(ctx, m, engine.revise, intent=body.intent, reason="user_correction",
                confirmed=body.confirm_transcript or body.intent is not None)


@router.post("/{mission_id}/approve")
def approve(mission_id: str, body: ApproveIn, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.approve", m.id, {"actions": [a.action_id for a in body.approvals]})
    return _run(ctx, m, engine.approve, ctx.user.id, [a.model_dump() for a in body.approvals])


@router.post("/{mission_id}/execute")
def execute(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.execute", m.id)
    return _run(ctx, m, engine.execute)


@router.post("/{mission_id}/reconcile")
def reconcile(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    return _run(ctx, m, engine.reconcile_mission)


@router.post("/{mission_id}/cancel")
def cancel(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    audit(ctx.db, ctx, "mission.cancel", m.id)
    return _run(ctx, m, engine.cancel)


@router.post("/{mission_id}/faults", status_code=201)
def inject_fault(mission_id: str, body: FaultIn, ctx: Ctx = Depends(current_ctx)):
    """Arms a one-shot fault on the *fixture* provider for this tenant (demo/test only)."""
    if not settings.allow_fault_injection:
        raise err(403, "fault_injection_disabled", "Fault injection is disabled in this deployment")
    m = _get(ctx, mission_id)
    if m.status in TERMINAL:
        raise err(409, "mission_final", "Mission already finished")
    from .ops import BROWSER_FAULTS, arm_browser_fault
    if body.kind in BROWSER_FAULTS:
        if m.scenario != "browser_followup":
            raise err(409, "not_a_browser_mission", "That fault applies to browser missions only")
        arm_browser_fault(ctx, m, body.kind)
    else:
        ctx.db.add(FxFault(tenant_id=ctx.tenant_id, kind=body.kind, remaining=1))
    engine.emit(ctx.db, m, "FAULT_ARMED", {"kind": body.kind, "scope": "fixture_provider"})
    audit(ctx.db, ctx, "mission.fault", m.id, {"kind": body.kind})
    ctx.db.commit()
    return {"armed": body.kind}


def _event_json(e: ActionEvent) -> dict:
    return {"seq": e.seq, "type": e.type, "action_id": e.action_id, "data": e.data,
            "created_at": e.created_at.isoformat()}


@router.get("/{mission_id}/events")
def events(mission_id: str, ctx: Ctx = Depends(current_ctx), after: int = Query(0, ge=0),
           limit: int = Query(200, ge=1, le=500)):
    m = _get(ctx, mission_id)
    rows = ctx.db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id, ActionEvent.seq > after)
                          .order_by(ActionEvent.seq).limit(limit))
    return {"items": [_event_json(e) for e in rows]}


@router.get("/{mission_id}/stream")
async def stream(mission_id: str, ctx: Ctx = Depends(current_ctx), after: int = Query(0, ge=0)):
    m = _get(ctx, mission_id)
    mid, tenant = m.id, ctx.tenant_id

    async def gen():
        cursor, idle = after, 0
        while idle < 120:  # ~60s max per connection; EventSource reconnects with Last-Event-ID semantics
            with SessionLocal() as db:
                rows = list(db.scalars(select(ActionEvent).where(
                    ActionEvent.mission_id == mid, ActionEvent.tenant_id == tenant, ActionEvent.seq > cursor)
                    .order_by(ActionEvent.seq).limit(100)))
                status = db.scalar(select(Mission.status).where(Mission.id == mid))
            for e in rows:
                cursor = e.seq
                yield f"id: {e.seq}\nevent: ledger\ndata: {json.dumps(_event_json(e), ensure_ascii=False)}\n\n"
            idle = 0 if rows else idle + 1
            if status in TERMINAL and not rows:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/{mission_id}/receipt")
def receipt(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _get(ctx, mission_id)
    if not m.outcome:
        raise err(404, "no_receipt", "No receipt yet: the mission has not produced an outcome")
    return {"mission_id": m.id, "intent": m.intent, "revision": m.revision, "outcome": m.outcome}
