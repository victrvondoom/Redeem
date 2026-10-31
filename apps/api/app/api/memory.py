from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select

from ..core.deps import Ctx, audit, current_ctx, err
from ..memory import extract, service
from ..models import Call, ConsentRecord, MemoryItem
from ..schemas import MemoryIngestIn, MemoryPatchIn

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _consented(ctx: Ctx) -> bool:
    row = ctx.db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == ctx.user.id, ConsentRecord.purpose == "memory_capture")
                        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc()))
    return bool(row and row.granted)


def _mine(ctx: Ctx, mem_id: str) -> MemoryItem:
    m = service.get(ctx.db, ctx, mem_id)
    if not m:
        raise err(404, "not_found", "No such memory item")
    return m


@router.get("")
def list_memory(ctx: Ctx = Depends(current_ctx), q: str | None = Query(None, max_length=100), category: str | None = None, status: str | None = Query(None, pattern="^(proposed|confirmed|rejected)$")):
    items = service.listing(ctx.db, ctx, q, category, status)
    ctx.db.commit()
    return {"items": items, "capture_consent": _consented(ctx), "fields": extract.registry()}


@router.post("/ingest", status_code=201)
def ingest(body: MemoryIngestIn, ctx: Ctx = Depends(current_ctx)):
    """Map an answer to a structured field. With `call_id` the answer is attributed to that Bolna call (requires memory_capture consent);
    `fixture=true` marks it as a simulated Bolna answer; otherwise it is the user's own typed answer."""
    kind, ref = "typed", None
    if body.call_id:
        call = ctx.db.scalar(select(Call).where(Call.id == body.call_id, Call.tenant_id == ctx.tenant_id, Call.user_id == ctx.user.id))
        if not call:
            raise err(404, "not_found", "No such call")
        if not _consented(ctx):
            raise err(403, "consent_required", "Grant memory-capture consent before saving answers from calls")
        kind, ref = "bolna_call", call.id
    elif body.fixture:
        kind = "bolna_fixture"
    r = service.ingest(ctx.db, ctx, body.utterance, body.expected_field, kind, ref, body.segment, body.retention_days)
    audit(ctx.db, ctx, "memory.ingest", None, {"fields": [s["field"] for s in r["saved"]], "source": kind})
    ctx.db.commit()
    return r


@router.post("/consent", status_code=201)
def consent(granted: bool = Query(...), ctx: Ctx = Depends(current_ctx)):
    ctx.db.add(ConsentRecord(tenant_id=ctx.tenant_id, user_id=ctx.user.id, purpose="memory_capture", granted=granted))
    audit(ctx.db, ctx, "consent.set", "memory_capture", {"granted": granted})
    ctx.db.commit()
    return {"purpose": "memory_capture", "granted": granted}


@router.post("/from-call/{call_id}", status_code=201)
def from_call(call_id: str, ctx: Ctx = Depends(current_ctx)):
    call = ctx.db.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == ctx.tenant_id, Call.user_id == ctx.user.id))
    if not call:
        raise err(404, "not_found", "No such call")
    if not _consented(ctx):
        raise err(403, "consent_required", "Grant memory-capture consent first")
    saved = service.ingest_transcript(ctx.db, ctx, call)
    audit(ctx.db, ctx, "memory.from_call", call_id, {"count": len(saved)})
    ctx.db.commit()
    return {"saved": saved, "note": "Only the caller's own lines were read. Nothing sensitive is used until you confirm it."}


@router.get("/relevant")
def relevant(intent: str = Query(..., max_length=500), ctx: Ctx = Depends(current_ctx)):
    return {"items": service.relevant(ctx.db, ctx, intent), "note": "Confirmed memory only."}


@router.post("/{mem_id}/confirm")
def confirm(mem_id: str, body: MemoryPatchIn | None = None, ctx: Ctx = Depends(current_ctx)):
    m = _mine(ctx, mem_id)
    try:
        out = service.confirm(ctx.db, ctx, m, body.value if body else None)
    except ValueError:
        raise err(422, "invalid_value", "Value required")
    audit(ctx.db, ctx, "memory.confirm", mem_id)
    ctx.db.commit()
    return out


@router.post("/{mem_id}/reject")
def reject(mem_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _mine(ctx, mem_id)
    m.status = "rejected"
    audit(ctx.db, ctx, "memory.reject", mem_id)
    ctx.db.commit()
    return service._json(ctx.db, ctx.tenant_id, m)


@router.patch("/{mem_id}")
def patch(mem_id: str, body: MemoryPatchIn, ctx: Ctx = Depends(current_ctx)):
    m = _mine(ctx, mem_id)
    if body.pinned is not None:
        m.pinned = body.pinned
    if body.value is not None:
        service.confirm(ctx.db, ctx, m, body.value)
    audit(ctx.db, ctx, "memory.edit", mem_id)
    ctx.db.commit()
    return service._json(ctx.db, ctx.tenant_id, m)


@router.delete("/{mem_id}", status_code=204)
def delete_one(mem_id: str, ctx: Ctx = Depends(current_ctx)):
    m = _mine(ctx, mem_id)
    ctx.db.delete(m)
    audit(ctx.db, ctx, "memory.delete", mem_id)
    ctx.db.commit()


@router.delete("")
def delete_category(category: str = Query(..., max_length=30), ctx: Ctx = Depends(current_ctx)):
    r = ctx.db.execute(delete(MemoryItem).where(MemoryItem.tenant_id == ctx.tenant_id, MemoryItem.user_id == ctx.user.id, MemoryItem.category == category))
    audit(ctx.db, ctx, "memory.delete_category", category, {"count": r.rowcount})
    ctx.db.commit()
    return {"deleted": r.rowcount}
