from fastapi import APIRouter, Depends, Query

from ..core.deps import Ctx, audit, current_ctx
from ..memory import context

router = APIRouter(prefix="/api/v1", tags=["history"])


@router.get("/timeline")
def timeline(ctx: Ctx = Depends(current_ctx), kind: str | None = Query(None, pattern="^(mission|case|call|document|memory|conversation|activity)$"),
             q: str | None = Query(None, max_length=100), limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return context.timeline(ctx.db, ctx, kind, q, limit, offset)


@router.get("/context")
def get_context(ctx: Ctx = Depends(current_ctx), limit: int = Query(30, ge=1, le=200), channel: str | None = Query(None, pattern="^(mission|voice|memory|command)$"), ref_id: str | None = Query(None, max_length=40)):
    return {"turns": context.recent(ctx.db, ctx, limit, channel, ref_id), "note": "Your own conversation context, encrypted at rest. Used so follow-ups keep their context."}


@router.delete("/context")
def forget_context(ctx: Ctx = Depends(current_ctx), ref_id: str | None = Query(None, max_length=40)):
    n = context.forget(ctx.db, ctx, ref_id)
    audit(ctx.db, ctx, "context.forget", ref_id, {"count": n})
    ctx.db.commit()
    return {"deleted": n}


@router.get("/graph")
def get_graph(ctx: Ctx = Depends(current_ctx)):
    return context.graph(ctx.db, ctx)
