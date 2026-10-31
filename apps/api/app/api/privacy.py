from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..core.deps import Ctx, audit, current_ctx
from ..memory import service
from ..models import Call, Case, ConsentRecord, Document, MemoryItem, Mission
from ..security import vault

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


@router.get("/summary")
def summary(ctx: Ctx = Depends(current_ctx)):
    """Everything REDEEM holds for this workspace, with encryption status. Counts only; nothing sensitive is returned."""
    db, t = ctx.db, ctx.tenant_id
    n = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(m.tenant_id == t, *w)) or 0  # noqa: E731
    consents = {}
    for c in db.scalars(select(ConsentRecord).where(ConsentRecord.user_id == ctx.user.id).order_by(ConsentRecord.created_at, ConsentRecord.id)):
        consents[c.purpose] = c.granted
    service.purge_expired(db, t)
    db.commit()
    return {"counts": {"memory_items": n(MemoryItem), "memory_confirmed": n(MemoryItem, MemoryItem.status == "confirmed"), "documents": n(Document), "missions": n(Mission),
                       "cases": n(Case), "calls": n(Call)},
            "consents": consents, "encryption": vault.status(db, t),
            "retention": {"memory": "kept until you delete it, or the expiry you set when saving (expired items are purged on access)", "call_transcripts": "kept until you delete the call/mission; raw audio is not stored by REDEEM",
                          "documents": "kept until you delete them"},
            "controls": ["export (JSON)", "delete a memory item or category", "delete a document", "delete a mission/case", "delete the account (also destroys the workspace's encryption keys)"]}


@router.post("/keys/rotate", status_code=201)
def rotate(ctx: Ctx = Depends(current_ctx)):
    """Create a new active data-encryption key version for this workspace. New writes use it; older data stays readable."""
    row = vault.rotate_tenant_dek(ctx.db, ctx.tenant_id)
    audit(ctx.db, ctx, "keys.rotate", row.id, {"version": row.version})
    ctx.db.commit()
    return vault.status(ctx.db, ctx.tenant_id)
