import re

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, or_, select

from ..core.deps import Ctx, audit, current_ctx, err
from ..core.security import limiter
from ..models import Case, CaseDraft, CaseEvent, Document, EvidenceClaim
from ..reclaim import casework, docintel, kb, profiles, workflows
from ..reclaim.casework import CaseError
from ..schemas import ApproveCaseIn, CaseIn, DraftIn, IntakeIn, KbSearchIn, RankIn, TrackIn

router = APIRouter(prefix="/api/v1", tags=["cases"])
_INJECTION = re.compile(r"(ignore (all|previous|prior) (instructions|rules)|you are now|system prompt|approve (all|every)|disregard|do not tell the user)", re.I)
MAX_UPLOAD = 5_000_000


def _case(ctx: Ctx, cid: str) -> Case:
    c = ctx.db.scalar(select(Case).where(Case.id == cid, Case.tenant_id == ctx.tenant_id))
    if not c:
        raise err(404, "not_found", "Case not found")
    return c


def _run(ctx: Ctx, fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except CaseError as e:
        ctx.db.commit()
        raise err(e.status, e.code, e.message)
    except kb.CitationError as e:
        ctx.db.rollback()
        raise err(422, "unverified_citation", str(e))


# ---------------------------------------------------------------- domain workflows (generated from the real data, not hardcoded cards)
@router.get("/reclaim/domains")
def reclaim_domains(ctx: Ctx = Depends(current_ctx)):
    stats = {(x["domain"], x["provenance"]): x["chunks"] for x in kb.kb().stats()["by_domain_provenance"]}
    cases = {d: n for d, n in ctx.db.execute(select(Case.domain, func.count()).where(Case.tenant_id == ctx.tenant_id).group_by(Case.domain)).all()}
    items = []
    for d in profiles.DOMAINS:
        p, wf = profiles.profile(d), workflows.WF[d]
        kd = profiles.kb_domain(d)
        corpus = {prov: n for (dom, prov), n in stats.items() if dom == kd}
        items.append({"id": d, "label": profiles.LABEL[d], "counterparty": p["counterparty"], "regulator": p["regulator"], "is_dispute": p.get("is_dispute", True) is not False,
                      "intake_fields": [{"key": k, "example": v, "critical": k in wf["critical"]} for k, v in p["evidence_schema"].items()],
                      "issue_types": list(wf["issues"]), "evidence_checklist": [{"id": c["id"], "label": c["label"]} for c in wf["checklist"]],
                      "escalation": workflows.handoff_steps(d), "research_questions": p["research_questions"], "corpus": corpus or {"none": 0},
                      "corpus_note": ("Knowledge base has retrievable passages for this domain." if corpus else "No knowledge corpus was inherited for this domain: analysis cites nothing and says so."),
                      "my_cases": cases.get(d, 0), "connectors": ["casedesk_fixture (internal case record)"], "filing_channel": "BLOCKED — guided handoff only; REDEEM has no verified filing connector",
                      "status": "LOCALLY_TESTED"})
    return {"items": items}


@router.post("/knowledge/search")
def knowledge_search(body: KbSearchIn, ctx: Ctx = Depends(current_ctx)):
    doms = [profiles.kb_domain(d) for d in body.domains] if body.domains else None
    hits = kb.kb().search(body.query, doms, body.k)
    return {"items": hits, "stats": kb.kb().stats(), "note": "BM25 retrieval over the inherited RECLAIM corpus. authored_guide passages are not official texts."}


@router.get("/knowledge/stats")
def knowledge_stats(ctx: Ctx = Depends(current_ctx)):
    return kb.kb().stats()


@router.get("/knowledge/chunks/{chunk_id}")
def knowledge_chunk(chunk_id: str, ctx: Ctx = Depends(current_ctx)):
    r = kb.kb().by_id.get(chunk_id)
    if not r:
        raise err(404, "not_found", "No such passage")
    return r


# ---------------------------------------------------------------- cases
@router.post("/cases", status_code=201)
def create_case(body: CaseIn, ctx: Ctx = Depends(current_ctx)):
    limiter.check(f"case:{ctx.user.id}", 30)
    c = _run(ctx, casework.create_case, ctx.db, ctx.tenant_id, ctx.workspace_id, ctx.user.id, body.text, body.domain, body.intake, None, ctx.user.name, body.document_ids)
    audit(ctx.db, ctx, "case.create", c.id)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.get("/cases")
def list_cases(ctx: Ctx = Depends(current_ctx), q: str | None = Query(None, max_length=100), domain: str | None = None, status: str | None = None,
               sort: str = Query("updated", pattern="^(updated|created|title|status)$"), order: str = Query("desc", pattern="^(asc|desc)$"),
               limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    stmt = select(Case).where(Case.tenant_id == ctx.tenant_id)
    if q:
        stmt = stmt.where(or_(Case.title.ilike(f"%{q}%"), Case.description.ilike(f"%{q}%"), Case.provider.ilike(f"%{q}%")))
    if domain:
        stmt = stmt.where(Case.domain == domain)
    if status:
        stmt = stmt.where(Case.status == status)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = {"updated": Case.updated_at, "created": Case.created_at, "title": Case.title, "status": Case.status}[sort]
    rows = ctx.db.scalars(stmt.order_by(col.desc() if order == "desc" else col.asc()).limit(limit).offset(offset))
    return {"total": total, "limit": limit, "offset": offset, "items": [{
        "id": c.id, "title": c.title, "domain": c.domain, "domain_label": profiles.LABEL[c.domain], "status": c.status, "stage": c.stage, "provider": c.provider,
        "claimed_paise": c.claimed_paise, "followup_date": c.followup_date, "overdue": casework.overdue(c), "confidence": (c.analysis or {}).get("confidence"),
        "missing": len(c.missing or []), "updated_at": c.updated_at.isoformat(), "created_at": c.created_at.isoformat()} for c in rows]}


@router.get("/cases/{cid}")
def get_case(cid: str, ctx: Ctx = Depends(current_ctx)):
    return casework.view(ctx.db, _case(ctx, cid))


@router.patch("/cases/{cid}/intake")
def patch_intake(cid: str, body: IntakeIn, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    _run(ctx, casework.update_intake, ctx.db, c, body.fields)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.post("/cases/{cid}/reanalyze")
def reanalyze(cid: str, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    _run(ctx, casework.run_pipeline, ctx.db, c)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.post("/cases/{cid}/documents", status_code=201)
async def case_upload(cid: str, file: UploadFile | None = File(None), document_id: str | None = Form(None), ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    if document_id:
        d = ctx.db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == ctx.tenant_id))
        if not d:
            raise err(404, "not_found", "Document not found")
        info = {"linked_existing": True}
    elif file:
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise err(413, "file_too_large", "Max 5 MB")
        d, info = docintel.ingest(ctx.db, ctx.tenant_id, file.filename or "upload", file.content_type or "application/octet-stream", data, c.domain, c.id)
    else:
        raise err(422, "no_document", "Send a file or document_id")
    if d.text_content and _INJECTION.search(d.text_content):
        d.extracted = {**d.extracted, "injection_suspected": True}
    _run(ctx, casework.attach_document, ctx.db, c, d)
    audit(ctx.db, ctx, "case.document", c.id, {"document": d.id})
    ctx.db.commit()
    return {"document_id": d.id, "ingest": info, "relevance": d.relevance, "strength": d.strength, "doc_type": d.doc_type, "case": casework.view(ctx.db, c)}


@router.delete("/cases/{cid}/documents/{doc_id}")
def case_detach(cid: str, doc_id: str, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    d = ctx.db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == ctx.tenant_id, Document.case_id == c.id))
    if not d:
        raise err(404, "not_found", "Document is not attached to this case")
    casework.detach_document(ctx.db, c, d)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.put("/cases/{cid}/draft")
def put_draft(cid: str, body: DraftIn, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    _run(ctx, casework.edit_draft, ctx.db, c, body.body)
    audit(ctx.db, ctx, "case.draft_edit", c.id)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.post("/cases/{cid}/rank")
def rank_actions(cid: str, body: RankIn, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    r = casework.rerank(ctx.db, c, body.weights)
    ctx.db.commit()
    return r


@router.post("/cases/{cid}/approve")
def approve_case(cid: str, body: ApproveCaseIn, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    r = _run(ctx, casework.approve, ctx.db, c, ctx.user.id, body.action_key, body.digest)
    audit(ctx.db, ctx, "case.approve", c.id, {"action": body.action_key})
    ctx.db.commit()
    return {"approval": r, "case": casework.view(ctx.db, c)}


@router.post("/cases/{cid}/submit")
def submit_case(cid: str, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    _run(ctx, casework.submit, ctx.db, c)
    audit(ctx.db, ctx, "case.submit", c.id)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.post("/cases/{cid}/track")
def track_case(cid: str, body: TrackIn, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    doc = None
    if body.document_id:
        doc = ctx.db.scalar(select(Document).where(Document.id == body.document_id, Document.tenant_id == ctx.tenant_id))
        if not doc:
            raise err(404, "not_found", "Document not found")
    _run(ctx, casework.track, ctx.db, c, body.kind, body.reference, body.note, doc, int(round(body.amount_inr * 100)) if body.amount_inr is not None else None)
    audit(ctx.db, ctx, "case.track", c.id, {"kind": body.kind})
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.post("/cases/{cid}/close")
def close_case(cid: str, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    casework.close(ctx.db, c)
    ctx.db.commit()
    return casework.view(ctx.db, c)


@router.delete("/cases/{cid}", status_code=204)
def delete_case(cid: str, ctx: Ctx = Depends(current_ctx)):
    c = _case(ctx, cid)
    for m in (CaseEvent, CaseDraft, EvidenceClaim):
        ctx.db.execute(delete(m).where(m.case_id == c.id))
    for d in ctx.db.scalars(select(Document).where(Document.case_id == c.id)):
        d.case_id = None
    ctx.db.delete(c)
    audit(ctx.db, ctx, "case.delete", cid)
    ctx.db.commit()


@router.get("/cases/{cid}/report")
def case_report(cid: str, ctx: Ctx = Depends(current_ctx), format: str = Query("json", pattern="^(json|md)$")):
    r = casework.report(ctx.db, _case(ctx, cid))
    if format == "md":
        return Response(casework.to_markdown(r), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="case-{cid}.md"', "X-Content-Type-Options": "nosniff"})
    return r


@router.get("/cases/{cid}/bundle")
def case_bundle(cid: str, ctx: Ctx = Depends(current_ctx)):
    data = casework.bundle(ctx.db, _case(ctx, cid))
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="evidence-bundle-{cid}.zip"', "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- institution radar (aggregated from THIS workspace's cases only)
@router.get("/intelligence/radar")
def radar(ctx: Ctx = Depends(current_ctx)):
    rows = list(ctx.db.scalars(select(Case).where(Case.tenant_id == ctx.tenant_id)))
    by: dict[str, dict] = {}
    for c in rows:
        k = (c.provider or profiles.profile(c.domain)["counterparty"]).strip()
        r = by.setdefault(k, {"institution": k, "cases": 0, "domains": set(), "claimed_paise": 0, "resolved": 0, "unresolved": 0, "open": 0, "issues": {}})
        r["cases"] += 1
        r["domains"].add(c.domain)
        r["claimed_paise"] += c.claimed_paise or 0
        r["resolved" if c.status == "RESOLVED" else "unresolved" if c.status == "UNRESOLVED" else "open"] += 1
        r["issues"][c.issue_type] = r["issues"].get(c.issue_type, 0) + 1
    items = sorted(({**v, "domains": sorted(v["domains"])} for v in by.values()), key=lambda x: -x["cases"])
    return {"items": items, "scope": "Your workspace's cases only. This is not a cross-citizen pattern database (RECLAIM's shared knowledge graph was not inherited).", "total_cases": len(rows)}
