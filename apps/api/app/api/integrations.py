from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ..core.deps import Ctx, audit, current_ctx, err
from ..integrations import service as svc
from ..models import ExternalAction
from ..schemas import ActionCreateIn, ApproveActionIn, GoogleConnectIn

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _run(fn, *a):
    try:
        return fn(*a)
    except svc.IntegrationError as e:
        raise err(e.status, e.code, e.message)


@router.get("")
def providers(ctx: Ctx = Depends(current_ctx)):
    return svc.status(ctx.db, ctx)


@router.post("/google/connect")
def google_connect(body: GoogleConnectIn, ctx: Ctx = Depends(current_ctx)):
    url = _run(svc.connect_start, ctx.db, ctx, body.capabilities)
    audit(ctx.db, ctx, "integration.connect_start", "google", {"capabilities": body.capabilities})
    ctx.db.commit()
    return {"auth_url": url}


@router.get("/google/callback")
def google_callback(ctx: Ctx = Depends(current_ctx), state: str = Query("", max_length=200), code: str = Query("", max_length=2000), error: str | None = Query(None, max_length=100)):
    if error or not code or not state:
        return RedirectResponse(f"/app/connections?error={error or 'missing_code'}", status_code=302)
    try:
        svc.callback(ctx.db, ctx, state, code)
    except svc.IntegrationError as e:
        ctx.db.rollback()
        return RedirectResponse(f"/app/connections?error={e.code}", status_code=302)
    audit(ctx.db, ctx, "integration.connected", "google")
    ctx.db.commit()
    return RedirectResponse("/app/connections?connected=google", status_code=302)


@router.post("/google/test")
def google_test(ctx: Ctx = Depends(current_ctx)):
    out = _run(svc.test_connection, ctx.db, ctx)
    audit(ctx.db, ctx, "integration.test", "google")
    ctx.db.commit()
    return out


@router.post("/google/disconnect")
def google_disconnect(ctx: Ctx = Depends(current_ctx)):
    out = _run(svc.disconnect, ctx.db, ctx)
    audit(ctx.db, ctx, "integration.revoke", "google", out)
    ctx.db.commit()
    return out


@router.post("/actions", status_code=201)
def create_action(body: ActionCreateIn, ctx: Ctx = Depends(current_ctx)):
    a = _run(svc.create_action, ctx.db, ctx, body.kind, body.params.model_dump())
    audit(ctx.db, ctx, "action.draft", a.id, {"kind": a.kind})
    ctx.db.commit()
    return svc.action_json(ctx.db, ctx, a)


@router.get("/actions")
def list_actions(ctx: Ctx = Depends(current_ctx), limit: int = Query(30, ge=1, le=100)):
    rows = ctx.db.scalars(select(ExternalAction).where(ExternalAction.tenant_id == ctx.tenant_id).order_by(ExternalAction.created_at.desc()).limit(limit))
    return {"items": [svc.action_json(ctx.db, ctx, a) for a in rows]}


def _mine(ctx: Ctx, action_id: str) -> ExternalAction:
    a = svc.get_action(ctx.db, ctx, action_id)
    if not a:
        raise err(404, "not_found", "No such action")
    return a


@router.get("/actions/{action_id}")
def get_action(action_id: str, ctx: Ctx = Depends(current_ctx)):
    return svc.action_json(ctx.db, ctx, _mine(ctx, action_id))


@router.post("/actions/{action_id}/approve")
def approve(action_id: str, body: ApproveActionIn, ctx: Ctx = Depends(current_ctx)):
    a = _run(svc.approve, ctx.db, ctx, _mine(ctx, action_id), body.digest)
    audit(ctx.db, ctx, "action.approve", a.id)
    ctx.db.commit()
    return svc.action_json(ctx.db, ctx, a)


@router.post("/actions/{action_id}/execute")
def execute(action_id: str, ctx: Ctx = Depends(current_ctx)):
    a = _run(svc.execute, ctx.db, ctx, _mine(ctx, action_id))
    audit(ctx.db, ctx, "action.execute", a.id, {"status": a.status})
    ctx.db.commit()
    return svc.action_json(ctx.db, ctx, a)


@router.post("/actions/{action_id}/reconcile")
def reconcile(action_id: str, ctx: Ctx = Depends(current_ctx)):
    a = _run(svc.reconcile, ctx.db, ctx, _mine(ctx, action_id))
    audit(ctx.db, ctx, "action.reconcile", a.id, {"status": a.status})
    ctx.db.commit()
    return svc.action_json(ctx.db, ctx, a)
