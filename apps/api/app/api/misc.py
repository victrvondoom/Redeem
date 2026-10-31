import json
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, or_, select, text

from ..config import settings
from ..core.deps import Ctx, audit, current_ctx, err
from ..db import get_db, utcnow
from ..domains.language import SUPPORTED_LANGUAGES
from ..domains.registry import list_domains
from ..models import (Action, ActionApproval, ActionEvent, AuditEvent, AuthSession, Call, CallEvent, ConsentRecord,
                      Connection, Document, FxBooking, FxCustomer, FxFault, FxProduct, FxRequest, FxReservation,
                      Membership, Mission, MissionRevision, ProviderOperation, Tenant, User, VerificationClaim,
                      Workspace)
from ..models import FxCalendarEvent, FxCase, FxContact, FxFlightOption, FxLead, FxMessage
from ..policy.payment_safety import scan
from ..reclaim import docintel
from ..models import Case, CaseDraft, CaseEvent, EvidenceClaim
from ..schemas import ScanIn

router = APIRouter(prefix="/api/v1", tags=["platform"])

_INJECTION = re.compile(r"(ignore (all|previous|prior) (instructions|rules)|you are now|system prompt|"
                        r"approve (all|every)|disregard|do not tell the user)", re.I)
MAX_UPLOAD = 5_000_000


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


# ---------------------------------------------------------------- documents (Evidence Vault, inherited document intelligence)
def _doc_json(d: Document, detail: bool = False) -> dict:
    out = {"id": d.id, "filename": d.filename, "content_type": d.content_type, "sha256": d.sha256, "version": d.version, "size": d.size, "extracted": d.extracted,
           "case_id": d.case_id, "domain": d.domain, "doc_type": d.doc_type, "strength": d.strength, "relevance": d.relevance, "ocr_status": d.ocr_status,
           "page_count": d.page_count, "supersedes": d.supersedes, "near_duplicate_of": (d.fields or {}).get("near_duplicate_of"), "created_at": d.created_at.isoformat(),
           "fact_count": len((d.fields or {}).get("facts", []))}
    if detail:
        out["facts"] = (d.fields or {}).get("facts", [])
        out["text"] = (d.text_content or "")[:20000]
    return out


@router.post("/documents", status_code=201)
async def upload(file: UploadFile = File(...), domain: str | None = None, ctx: Ctx = Depends(current_ctx)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise err(413, "file_too_large", "Max 5 MB")
    d, info = docintel.ingest(ctx.db, ctx.tenant_id, file.filename or "upload", file.content_type or "application/octet-stream", data, domain)
    if d.text_content and _INJECTION.search(d.text_content):
        d.extracted = {**d.extracted, "injection_suspected": True}
    audit(ctx.db, ctx, "document.upload", d.id)
    ctx.db.commit()
    return {**_doc_json(d), "ingest": info}


@router.get("/documents")
def list_documents(ctx: Ctx = Depends(current_ctx), q: str | None = Query(None, max_length=100), domain: str | None = None, doc_type: str | None = None,
                   case_id: str | None = None, sort: str = Query("created", pattern="^(created|strength|name)$"), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    stmt = select(Document).where(Document.tenant_id == ctx.tenant_id)
    if q:
        stmt = stmt.where(or_(Document.filename.ilike(f"%{q}%"), Document.text_content.ilike(f"%{q}%")))
    if domain:
        stmt = stmt.where(Document.domain == domain)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if case_id:
        stmt = stmt.where(Document.case_id == case_id)
    rows = list(ctx.db.scalars(stmt.order_by(Document.created_at.desc())))
    if sort == "strength":
        rows.sort(key=lambda d: -((d.strength or {}).get("score", 0)))
    elif sort == "name":
        rows.sort(key=lambda d: d.filename.lower())
    return {"total": len(rows), "items": [_doc_json(d) for d in rows[offset: offset + limit]]}


def _doc(ctx: Ctx, doc_id: str) -> Document:
    d = ctx.db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == ctx.tenant_id))
    if not d:
        raise err(404, "not_found", "Document not found")
    return d


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    d = _doc(ctx, doc_id)
    versions = [{"id": v.id, "version": v.version, "sha256": v.sha256[:12], "created_at": v.created_at.isoformat()}
                for v in ctx.db.scalars(select(Document).where(Document.tenant_id == ctx.tenant_id, Document.filename == d.filename).order_by(Document.version))]
    claims = [c for c in ctx.db.scalars(select(EvidenceClaim).where(EvidenceClaim.tenant_id == ctx.tenant_id)) if any(s.get("id") == d.id for s in (c.support or []))]
    return {**_doc_json(d, True), "versions": versions, "supports_claims": [{"claim": c.claim, "status": c.status, "case_id": c.case_id} for c in claims]}


@router.get("/documents/{doc_id}/download")
def download(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    d = _doc(ctx, doc_id)
    body, ctype = (b"", "text/plain")
    if d.blob_path and Path(d.blob_path).is_file() and Path(d.blob_path).resolve().is_relative_to(Path(settings.data_dir).resolve()):
        body, ctype = Path(d.blob_path).read_bytes(), "application/octet-stream"
    else:
        body = (d.text_content or "").encode()
    return Response(body, media_type=ctype, headers={"Content-Disposition": f'attachment; filename="{d.filename}"', "X-Content-Type-Options": "nosniff"})


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    d = _doc(ctx, doc_id)
    cid = d.case_id
    others = ctx.db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == ctx.tenant_id, Document.sha256 == d.sha256, Document.id != d.id)) or 0
    if d.blob_path and not others and Path(d.blob_path).is_file():
        Path(d.blob_path).unlink(missing_ok=True)
    ctx.db.delete(d)
    audit(ctx.db, ctx, "document.delete", doc_id)
    ctx.db.commit()
    if cid:
        from ..reclaim import casework as _cw
        c = ctx.db.get(Case, cid)
        if c:
            _cw.run_pipeline(ctx.db, c)
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
    bench_path = Path(__file__).resolve().parents[4] / "evals" / "reports" / "benchmark_results.json"
    bench = None
    if bench_path.exists():
        b = json.loads(bench_path.read_text())
        bench = {"generated_at": b["generated_at"], "seed": b["seed"], "trials_per_cell": b["trials_per_cell"],
                 "scope": b["scope"], "caveat": b["caveat"], "ablations": b.get("ablations"), "summary": b["summary"]}
    return {
        "benchmark": bench,
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
        "cases": [{"id": c.id, "title": c.title, "domain": c.domain, "status": c.status, "intake": c.intake, "outcome": c.outcome} for c in db.scalars(select(Case).where(Case.tenant_id == t))],
        "calls": [{"id": c.id, "status": c.status, "transcript": c.transcript}
                  for c in db.scalars(select(Call).where(Call.tenant_id == t))],
        "consents": [{"purpose": c.purpose, "granted": c.granted, "at": c.created_at.isoformat()}
                     for c in db.scalars(select(ConsentRecord).where(ConsentRecord.tenant_id == t))],
    }


def _purge_tenant(db, t: str) -> None:
    for model in (CallEvent, VerificationClaim, ProviderOperation, ActionApproval, ActionEvent, Action,
                  MissionRevision, Mission, Document, Call, ConsentRecord, FxFault, FxRequest, FxReservation,
                  FxBooking, FxProduct, FxCustomer, FxCalendarEvent, FxLead, FxCase, FxContact, FxMessage, FxFlightOption, RegSource, Connection, CaseEvent, CaseDraft, EvidenceClaim, Case):
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
    shutil.rmtree(Path(settings.data_dir) / "blobs" / t, ignore_errors=True)
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


# ---------------------------------------------------------------- workflows, safety, sources, browser gate
from ..domains.workflows import get_workflow, list_workflows  # noqa: E402
from ..models import Mission as _Mission, RegSource  # noqa: E402
from ..orchestration import engine as _engine  # noqa: E402
from ..policy import safety, ssrf  # noqa: E402
from ..schemas import StartWorkflowIn, UrlCheckIn  # noqa: E402


@router.get("/workflows")
def workflows(ctx: Ctx = Depends(current_ctx)):
    return {"items": list_workflows()}


@router.post("/workflows/{workflow_id}/start", status_code=201)
def start_workflow(workflow_id: str, body: StartWorkflowIn, ctx: Ctx = Depends(current_ctx)):
    w = get_workflow(workflow_id)
    if not w:
        raise err(404, "not_found", "Unknown workflow")
    missing = [k for k in w.inputs if not str(body.inputs.get(k, "")).strip()]
    if missing:
        raise err(422, "missing_inputs", f"Missing inputs: {', '.join(missing)}", missing=missing)
    try:
        intent = w.intent_template.format(**{k: str(body.inputs[k])[:300] for k in w.inputs})
    except KeyError as e:  # pragma: no cover
        raise err(422, "bad_inputs", str(e))
    m = _Mission(tenant_id=ctx.tenant_id, workspace_id=ctx.workspace_id, user_id=ctx.user.id, intent=intent,
                 language_selected=ctx.user.language)
    ctx.db.add(m)
    ctx.db.flush()
    audit(ctx.db, ctx, "workflow.start", workflow_id)
    try:
        _engine.start_mission(ctx.db, m)
    finally:
        ctx.db.commit()
    return {"workflow": workflow_id, "mission": _engine.mission_view(ctx.db, m)}


@router.post("/safety/evaluate-content")
def evaluate_content(body: ScanIn, ctx: Ctx = Depends(current_ctx)):
    return safety.evaluate_untrusted_content(body.text).as_dict()


@router.post("/safety/check-url")
def check_url(body: UrlCheckIn, ctx: Ctx = Depends(current_ctx)):
    try:
        ssrf.validate_url(body.url)
        return {"allowed": True}
    except ssrf.UnsafeURL as e:
        return {"allowed": False, "reason": str(e)}


@router.get("/browser/status")
def browser_status(ctx: Ctx = Depends(current_ctx)):
    ok, why = ssrf.browser_execution_allowed()
    return {"cloud_browser": "AVAILABLE" if ok else "BLOCKED", "reason": why}


@router.get("/sources")
def sources(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(RegSource).where(RegSource.tenant_id == ctx.tenant_id))
    return {"items": [{"id": r.id, "url": r.url, "title": r.title, "authority": r.authority, "published": r.published,
                       "passage": r.passage, "is_fixture": r.is_fixture} for r in rows],
            "note": "Only fixture sources are loaded. No official regulatory corpus has been ingested; none is asserted."}
