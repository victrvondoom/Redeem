import hashlib
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select, text

from ..config import settings
from ..core.deps import Ctx, audit, current_ctx, err
from ..db import get_db, utcnow
from ..domains.language import SUPPORTED_LANGUAGES
from ..domains.registry import list_domains
from ..models import (Action, ActionApproval, ActionEvent, AuditEvent, AuthSession, Call, CallEvent, ConsentRecord,
                      Connection, Document, FxBooking, FxCustomer, FxFault, FxProduct, FxRequest, FxReservation,
                      Membership, Mission, MissionRevision, ProviderOperation, Tenant, User, VerificationClaim,
                      Workspace)
from ..policy.payment_safety import scan
from ..schemas import ScanIn

router = APIRouter(prefix="/api/v1", tags=["platform"])

_INJECTION = re.compile(r"(ignore (all|previous|prior) (instructions|rules)|you are now|system prompt|"
                        r"approve (all|every)|disregard|do not tell the user)", re.I)
MAX_UPLOAD = 2_000_000


@router.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok", "time": utcnow().isoformat()}


@router.get("/domains")
def domains(ctx: Ctx = Depends(current_ctx)):
    return {"items": list_domains(), "languages": SUPPORTED_LANGUAGES}


@router.post("/safety/scan")
def safety_scan(body: ScanIn, ctx: Ctx = Depends(current_ctx)):
    return scan(body.text)


# ---------------------------------------------------------------- connectors
@router.get("/connectors")
def connectors(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(Connection).where(Connection.tenant_id == ctx.tenant_id))
    items = [{"provider": c.provider, "kind": c.kind, "scopes": c.scopes, "status": c.status,
              "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
              "note": "Stateful local fixture — not an OAuth connection." if c.kind == "fixture" else ""} for c in rows]
    items.append({"provider": "bolna", "kind": "api_key", "scopes": ["voice:web_call", "voice:outbound"],
                  "status": "active" if settings.bolna_configured else "PROVIDER_NOT_CONFIGURED",
                  "note": "Server-side API key; never sent to the browser."})
    return {"items": items}


@router.post("/connectors/{provider}/revoke")
def revoke(provider: str, ctx: Ctx = Depends(current_ctx)):
    c = ctx.db.scalar(select(Connection).where(Connection.tenant_id == ctx.tenant_id, Connection.provider == provider))
    if not c:
        raise err(404, "not_found", "Connector not found")
    c.status, c.revoked_at = "revoked", utcnow()
    audit(ctx.db, ctx, "connector.revoke", provider)
    ctx.db.commit()
    return {"provider": provider, "status": c.status}


@router.post("/connectors/{provider}/reinstate")
def reinstate(provider: str, ctx: Ctx = Depends(current_ctx)):
    c = ctx.db.scalar(select(Connection).where(Connection.tenant_id == ctx.tenant_id, Connection.provider == provider))
    if not c:
        raise err(404, "not_found", "Connector not found")
    c.status, c.revoked_at = "active", None
    audit(ctx.db, ctx, "connector.reinstate", provider)
    ctx.db.commit()
    return {"provider": provider, "status": c.status}


# ---------------------------------------------------------------- documents (Evidence Vault)
def _doc_json(d: Document) -> dict:
    return {"id": d.id, "filename": d.filename, "content_type": d.content_type, "sha256": d.sha256,
            "version": d.version, "size": d.size, "extracted": d.extracted, "created_at": d.created_at.isoformat()}


@router.post("/documents", status_code=201)
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(current_ctx)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise err(413, "file_too_large", "Max 2 MB")
    name = re.sub(r"[^\w.\- ]", "_", file.filename or "upload")[:200]
    ctype = file.content_type or "application/octet-stream"
    content = None
    extracted: dict = {}
    if ctype.startswith("text/") or name.lower().endswith((".txt", ".md", ".csv")):
        content = data.decode("utf-8", errors="replace")
        extracted["booking_refs"] = sorted(set(re.findall(r"\b[A-Z]{2}\d{3,4}\b", content)))
        extracted["injection_suspected"] = bool(_INJECTION.search(content))
        extracted["note"] = "Text parsed with regexes only; content is data, never instructions."
    else:
        extracted["note"] = "Stored with hash. Text extraction for this file type is not implemented yet."
    prev = ctx.db.scalar(select(func.max(Document.version)).where(Document.tenant_id == ctx.tenant_id,
                                                                  Document.filename == name))
    d = Document(tenant_id=ctx.tenant_id, filename=name, content_type=ctype, sha256=hashlib.sha256(data).hexdigest(),
                 version=(prev or 0) + 1, size=len(data), text_content=content, extracted=extracted)
    ctx.db.add(d)
    audit(ctx.db, ctx, "document.upload", d.id)
    ctx.db.commit()
    return _doc_json(d)


@router.get("/documents")
def list_documents(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(Document).where(Document.tenant_id == ctx.tenant_id).order_by(Document.created_at.desc()))
    return {"items": [_doc_json(d) for d in rows]}


def _doc(ctx: Ctx, doc_id: str) -> Document:
    d = ctx.db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == ctx.tenant_id))
    if not d:
        raise err(404, "not_found", "Document not found")
    return d


@router.get("/documents/{doc_id}/download")
def download(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    d = _doc(ctx, doc_id)
    body = (d.text_content or "").encode()
    return Response(body, media_type="text/plain", headers={
        "Content-Disposition": f'attachment; filename="{d.filename}"', "X-Content-Type-Options": "nosniff"})


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    ctx.db.delete(_doc(ctx, doc_id))
    audit(ctx.db, ctx, "document.delete", doc_id)
    ctx.db.commit()


# ---------------------------------------------------------------- quality lab
@router.get("/quality")
def quality(ctx: Ctx = Depends(current_ctx)):
    t, db = ctx.tenant_id, ctx.db
    missions = list(db.scalars(select(Mission).where(Mission.tenant_id == t)))
    by_status: dict[str, int] = {}
    by_lang: dict[str, dict] = {}
    for m in missions:
        by_status[m.status] = by_status.get(m.status, 0) + 1
        row = by_lang.setdefault(m.language_detected, {"missions": 0, "verified": 0})
        row["missions"] += 1
        row["verified"] += m.status == "VERIFIED"
    ev = list(db.scalars(select(ActionEvent).where(ActionEvent.tenant_id == t)))
    cnt = lambda ty: sum(1 for e in ev if e.type == ty)  # noqa: E731
    dispatched = cnt("DISPATCHING")
    verified = cnt("VERIFIED")
    dup = sum(1 for e in ev if e.type == "VERIFICATION_FAILED" and "duplicate" in str(e.data.get("reason", "")))
    durations = []
    for m in missions:
        if m.outcome:
            end = next((e.created_at for e in ev if e.mission_id == m.id and e.type == "RECEIPT"), None)
            if end:
                durations.append((end - m.created_at).total_seconds())
    calls = list(db.scalars(select(Call).where(Call.tenant_id == t)))
    costs = [c.cost for c in calls if c.cost is not None]
    NM = "Not measured"
    return {
        "fixture_results": {
            "label": "Local stateful fixtures — not live-provider results",
            "missions_total": len(missions), "missions_by_status": by_status,
            "actions_dispatched": dispatched, "actions_verified": verified,
            "verification_rate": round(verified / dispatched, 3) if dispatched else None,
            "acks_lost": cnt("ACK_LOST"), "reconciled_found": cnt("RECONCILED_FOUND"),
            "duplicate_actions_detected": dup, "approvals_invalidated": cnt("APPROVAL_INVALIDATED"),
            "revisions_created": cnt("REVISION_CREATED"),
            "mean_mission_seconds": round(sum(durations) / len(durations), 3) if durations else None,
            "wrong_target_rate": NM, "language_breakdown": by_lang,
        },
        "live_provider_results": {
            "label": "Bolna calls recorded by this workspace",
            "calls_total": len(calls), "calls_by_status": {s: sum(1 for c in calls if c.status == s) for s in {c.status for c in calls}},
            "calls_with_provider_cost": len(costs), "total_provider_cost": round(sum(costs), 4) if costs else None,
            "latency": NM, "asr_tts_component_timings": NM,
            "note": "No live-call metrics exist until a real Bolna call is made with credentials.",
        },
    }


# ---------------------------------------------------------------- privacy
@router.get("/privacy/export")
def export(ctx: Ctx = Depends(current_ctx)):
    t, db = ctx.tenant_id, ctx.db
    audit(db, ctx, "privacy.export")
    db.commit()
    return {
        "user": {"id": ctx.user.id, "email": ctx.user.email, "name": ctx.user.name},
        "missions": [{"id": m.id, "intent": m.intent, "status": m.status, "outcome": m.outcome}
                     for m in db.scalars(select(Mission).where(Mission.tenant_id == t))],
        "documents": [_doc_json(d) for d in db.scalars(select(Document).where(Document.tenant_id == t))],
        "calls": [{"id": c.id, "status": c.status, "transcript": c.transcript}
                  for c in db.scalars(select(Call).where(Call.tenant_id == t))],
        "consents": [{"purpose": c.purpose, "granted": c.granted, "at": c.created_at.isoformat()}
                     for c in db.scalars(select(ConsentRecord).where(ConsentRecord.tenant_id == t))],
    }


def _purge_tenant(db, t: str) -> None:
    for model in (CallEvent, VerificationClaim, ProviderOperation, ActionApproval, ActionEvent, Action,
                  MissionRevision, Mission, Document, Call, ConsentRecord, FxFault, FxRequest, FxReservation,
                  FxBooking, FxProduct, FxCustomer, Connection):
        db.execute(delete(model).where(model.tenant_id == t))


@router.delete("/privacy/missions/{mission_id}", status_code=204)
def delete_mission(mission_id: str, ctx: Ctx = Depends(current_ctx)):
    m = ctx.db.scalar(select(Mission).where(Mission.id == mission_id, Mission.tenant_id == ctx.tenant_id))
    if not m:
        raise err(404, "not_found", "Mission not found")
    ctx.db.execute(delete(ProviderOperation).where(
        ProviderOperation.action_id.in_(select(Action.id).where(Action.mission_id == m.id))))
    for model in (VerificationClaim, ActionApproval, ActionEvent, Action, MissionRevision):
        ctx.db.execute(delete(model).where(model.mission_id == m.id))
    ctx.db.delete(m)
    audit(ctx.db, ctx, "privacy.delete_mission", mission_id)
    ctx.db.commit()


@router.delete("/users/me", status_code=204)
def delete_account(response: Response, ctx: Ctx = Depends(current_ctx)):
    """Deletes the single-owner workspace's data and revokes every session."""
    t, uid = ctx.tenant_id, ctx.user.id
    audit(ctx.db, ctx, "account.delete", uid)
    _purge_tenant(ctx.db, t)
    ctx.db.execute(delete(AuthSession).where(AuthSession.user_id == uid))
    ctx.db.execute(delete(Membership).where(Membership.user_id == uid))
    ctx.db.execute(delete(Workspace).where(Workspace.tenant_id == t))
    ctx.db.execute(delete(Tenant).where(Tenant.id == t))
    user = ctx.db.get(User, uid)
    user.deleted_at, user.email, user.name = utcnow(), f"deleted+{uid}@invalid", "Deleted user"
    user.password_hash = "!"
    ctx.db.commit()
    response.delete_cookie("redeem_session", path="/")


@router.get("/audit")
def audit_log(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == ctx.tenant_id)
                          .order_by(AuditEvent.created_at.desc()).limit(100))
    return {"items": [{"action": a.action, "target": a.target, "at": a.created_at.isoformat()} for a in rows]}
