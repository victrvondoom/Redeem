"""Consumer case lifecycle (inherited from RECLAIM's case workflow, rebuilt on REDEEM's persistence, approvals and verification).

Stages (each persisted + logged to the case timeline):
 INTAKE > CLASSIFIED > ENTITIES_EXTRACTED > (NEEDS_INFO) > EVIDENCE_COLLECTED > SOURCES_RETRIEVED > EVIDENCE_SCORED > ANALYZED > DRAFTED > ACTIONS_RANKED >
 AWAITING_APPROVAL > APPROVED > SUBMITTED > TRACKING > OUTCOME_VERIFIED | OUTCOME_REPORTED_UNVERIFIED > CLOSED
Rules: no LLM; no invented law (only retrieved, hashed KB passages, cited by id); estimates are labelled assumptions; REDEEM has no verified filing
channel for any authority, so 'submit' = approval-bound internal record + guided handoff, and the outcome is VERIFIED only with supporting evidence."""
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..connectors.base import canonical
from ..connectors.casedesk import CaseDeskConnector
from ..db import utcnow
from ..models import Case, CaseDraft, CaseEvent, Document, EvidenceClaim
from . import decision, kb, profiles, workflows

STAGES = ["INTAKE", "CLASSIFIED", "ENTITIES_EXTRACTED", "NEEDS_INFO", "EVIDENCE_COLLECTED", "SOURCES_RETRIEVED", "EVIDENCE_SCORED", "ANALYZED", "DRAFTED",
          "ACTIONS_RANKED", "AWAITING_APPROVAL", "APPROVED", "SUBMITTED", "TRACKING", "OUTCOME_VERIFIED", "OUTCOME_REPORTED_UNVERIFIED", "CLOSED"]
IST = timezone(timedelta(hours=5, minutes=30))
today = lambda: datetime.now(IST).date()  # noqa: E731


class CaseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def log(db: Session, c: Case, type_: str, data: dict | None = None) -> None:
    db.add(CaseEvent(tenant_id=c.tenant_id, case_id=c.id, type=type_, data=data or {}))
    db.flush()


def set_stage(db: Session, c: Case, stage: str, data: dict | None = None) -> None:
    c.stage = stage
    log(db, c, "STAGE", {"stage": stage, **(data or {})})


def _docs(db: Session, c: Case) -> list[Document]:
    rows = list(db.scalars(select(Document).where(Document.case_id == c.id, Document.tenant_id == c.tenant_id, Document.duplicate_of.is_(None)).order_by(Document.created_at)))
    latest: dict[str, Document] = {}
    for d in rows:  # version history: only the newest version of a filename counts as current evidence
        if d.filename not in latest or d.version > latest[d.filename].version:
            latest[d.filename] = d
    return list(latest.values())


def fill_intake(domain: str, ents: dict, issue: str, existing: dict, text: str = "") -> dict:
    prof = profiles.profile(domain)
    out = dict(existing)
    dates, amounts = list(ents["dates"]), list(ents["amounts"])
    ids = {i["kind"]: i["value"] for i in ents["ids"]}
    for key in prof["evidence_schema"]:
        if out.get(key):
            continue
        k = key.lower()
        if "date" in k and dates:
            out[key] = dates.pop(0)["iso"]
        elif any(x in k for x in ("amount", "bill", "coverage")) and amounts:
            out[key] = f"₹{amounts[0]['value_paise'] / 100:,.2f}"
        elif k in ("flight_number",) and "flight_no" in ids:
            out[key] = ids["flight_no"]
        elif "reference" in k and ("utr" in ids):
            out[key] = ids["utr"]
        elif k in ("disruption_type", "dispute_type") and issue != "other":
            out[key] = issue.replace("_", " ")
    import re as _re
    if "hospital" in prof["evidence_schema"] and not out.get("hospital"):
        m = _re.search(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)* Hospitals?(?:,? [A-Z][a-z]+)?)", text)
        hp = next((p["name"] for p in ents["providers"] if p["domain"] == "healthcare"), None)
        if m or hp:
            out["hospital"] = (m.group(1) if m else hp)
    if "reason_for_rejection" in prof["evidence_schema"] and not out.get("reason_for_rejection"):
        m = _re.search(r"(?:citing|because|on the grounds? of|reason (?:given )?(?:was|is)[:]?)\s+([^.\n]{5,140})", text, _re.I)
        if m:
            out["reason_for_rejection"] = m.group(1).strip()
    for key, kind in (("order_id", "order_id"), ("policy_number", "policy_no"), ("claim_number", "claim_no"), ("complaint_reference", "complaint_ref"), ("pnr", "pnr")):
        if kind in ids and not out.get(key):
            out[key] = ids[kind]
    if issue != "other" and not out.get("issue_type"):
        out["issue_type"] = issue.replace("_", " ")
    return out


QUESTIONS = {"flight_number": "What is the flight number (e.g. 6E-2134)?", "scheduled_date": "On which date was the flight scheduled?",
             "disruption_type": "Was it a cancellation, delay, denied boarding or baggage issue?", "transaction_date": "On which date did the transaction happen?",
             "transaction_amount": "What was the transaction amount?", "dispute_type": "Is it unauthorized, failed, duplicate or something else?",
             "hospital": "Which hospital was this at?", "coverage_requested": "How much was claimed?", "reason_for_rejection": "What reason did the insurer give?",
             "issue_type": "What exactly is the problem (billing, outage, deposit, delay…)?", "order_id": "What is the order ID?"}


def _claims(db: Session, c: Case, docs: list[Document]) -> list[dict]:
    db.execute(delete(EvidenceClaim).where(EvidenceClaim.case_id == c.id))
    out = []
    for field, val in (c.intake or {}).items():
        if not val or field == "issue_type":
            continue
        sup, contra = [], []
        k = field.lower()
        vs = str(val)
        vents = profiles.extract_entities(vs)
        for d in docs:
            fl = (d.fields or {}).get("facts", [])
            txt = d.text_content or ""
            if any(x in k for x in ("amount", "bill", "coverage")) and vents["amounts"]:
                want = vents["amounts"][0]["value_paise"]
                am = [f for f in fl if f["kind"] == "amount"]
                hit = next((f for f in am if f["value"] == want), None)
                if hit:
                    sup.append({"kind": "document", "id": d.id, "filename": d.filename, "quote": hit.get("quote"), "page": hit.get("page")})
                elif am and d.doc_type in ("bill", "receipt", "invoice", "ticket", "medical_bill", "statement"):
                    contra.append({"kind": "document", "id": d.id, "filename": d.filename, "note": "document shows " + ", ".join(f["display"] for f in am[:3])})
            elif "date" in k and vents["dates"]:
                want = vents["dates"][0]["iso"] if vents["dates"] else vs
                hit = next((f for f in fl if f["kind"] == "date" and f["value"] == want), None)
                if hit:
                    sup.append({"kind": "document", "id": d.id, "filename": d.filename, "quote": hit.get("quote"), "page": hit.get("page")})
            elif vs.lower() in txt.lower() or any(str(f["value"]).lower() == vs.lower() for f in fl):
                i = txt.lower().find(vs.lower())
                sup.append({"kind": "document", "id": d.id, "filename": d.filename, "quote": txt[max(0, i - 40): i + len(vs) + 40].replace("\n", " ") if i >= 0 else None})
        status = "CONTRADICTED" if contra and not sup else ("SUPPORTED" if sup else "UNSUPPORTED")
        row = EvidenceClaim(tenant_id=c.tenant_id, case_id=c.id, field=field, claim=f"{field.replace('_', ' ')}: {vs}", status=status, support=sup or contra)
        db.add(row)
        out.append({"field": field, "claim": row.claim, "status": status, "support": sup or contra})
    return out


def _coverage(docs: list[Document], domain: str) -> tuple[list[dict], dict[str, float]]:
    chk = []
    cov = {}
    for item in workflows.WF[domain]["checklist"]:
        best, who = 0.0, None
        for d in docs:
            if d.doc_type in item["types"] and (d.strength or {}).get("score", 0) > best:
                best, who = d.strength["score"], d
        cov[item["id"]] = round(best, 2)
        chk.append({**item, "covered": best >= 0.35, "strength": round(best, 2), "document": {"id": who.id, "filename": who.filename} if who else None})
    return chk, cov


def create_case(db: Session, tenant_id: str, workspace_id: str, user_id: str, text: str, domain: str | None = None, intake: dict | None = None,
                mission_id: str | None = None, user_name: str = "", document_ids: list[str] | None = None) -> Case:
    cl = profiles.classify(text)
    if not domain:
        if not cl:
            raise CaseError(422, "domain_unclear", "I could not tell which area this belongs to. Pick a domain or add detail.")
        domain = cl[0]["domain"]
    if domain not in workflows.WF:
        raise CaseError(422, "unsupported_domain", f"No case workflow for '{domain}'.")
    ents = profiles.extract_entities(text, domain)
    issue = workflows.detect_issue(domain, text)
    provider = (ents["providers"][0]["name"] if ents["providers"] else None)
    c = Case(tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id, mission_id=mission_id, domain=domain, issue_type=issue, description=text.strip(),
             title=f"{profiles.LABEL[domain]}: {issue.replace('_', ' ')}" + (f" — {provider}" if provider else ""), provider=provider, intake=dict(intake or {}))
    db.add(c)
    db.flush()
    log(db, c, "CASE_CREATED", {"text": text[:500], "user_name": user_name, "classification": cl[:3]})
    set_stage(db, c, "INTAKE")
    for did in document_ids or []:
        d = db.scalar(select(Document).where(Document.id == did, Document.tenant_id == tenant_id))
        if d:
            d.case_id = c.id
            d.domain = d.domain or domain
    c.intake = {**c.intake, "_user_name": user_name} if user_name else c.intake
    run_pipeline(db, c)
    return c


def run_pipeline(db: Session, c: Case) -> None:
    domain, wf = c.domain, workflows.WF[c.domain]
    prof = profiles.profile(domain)
    docs = _docs(db, c)
    cl = profiles.classify(c.description)
    set_stage(db, c, "CLASSIFIED", {"domain": domain, "all_domains": [x["domain"] for x in cl[:4]], "issue_type": c.issue_type})
    text_all = c.description + "\n" + "\n".join((d.text_content or "")[:4000] for d in docs)
    ents = profiles.extract_entities(text_all, domain)
    c.entities = {"amounts": ents["amounts"][:8], "dates": ents["dates"][:8], "ids": ents["ids"][:12], "providers": ents["providers"][:4]}
    if not c.provider and ents["providers"]:
        c.provider = ents["providers"][0]["name"]
    c.intake = fill_intake(domain, ents, c.issue_type, c.intake or {}, text_all)
    amts = [a["value_paise"] for a in ents["amounts"]]
    c.claimed_paise = c.claimed_paise or (max(amts) if amts else None)
    ds = sorted(x["iso"] for x in ents["dates"])
    c.incident_date = c.incident_date or (ds[0] if ds else None)
    set_stage(db, c, "ENTITIES_EXTRACTED", {"amounts": len(ents["amounts"]), "dates": len(ents["dates"]), "ids": len(ents["ids"]), "providers": len(ents["providers"])})
    miss = [k for k in wf["critical"] if not (c.intake or {}).get(k)]
    c.missing = [{"field": k, "question": QUESTIONS.get(k, f"Please provide: {k.replace('_', ' ')}"), "example": prof["evidence_schema"].get(k)} for k in miss]
    if miss:
        c.status = "AWAITING_INFO"
        set_stage(db, c, "NEEDS_INFO", {"missing": miss})
    else:
        c.status = "OPEN" if c.status in ("AWAITING_INFO", "OPEN") else c.status
    chk, cov = _coverage(docs, domain)
    c.checklist = chk
    set_stage(db, c, "EVIDENCE_COLLECTED", {"documents": len(docs), "checklist_covered": sum(1 for x in chk if x["covered"]), "checklist_total": len(chk)})
    q = f"{c.description[:400]} {c.issue_type.replace('_', ' ')} {c.provider or ''} {prof['regulator']}"
    hits = kb.kb().search(q, domains=[profiles.kb_domain(domain)], k=5)
    c.sources = hits
    set_stage(db, c, "SOURCES_RETRIEVED", {"sources": len(hits), "provenance": sorted({h['provenance'] for h in hits}), "corpus_available": bool(hits)})
    claims = _claims(db, c, docs)
    set_stage(db, c, "EVIDENCE_SCORED", {"claims": len(claims), "supported": sum(1 for x in claims if x["status"] == "SUPPORTED"), "contradicted": sum(1 for x in claims if x["status"] == "CONTRADICTED")})
    avail = {k for k, v in cov.items() if v >= 0.35}
    days = (today() - date.fromisoformat(c.incident_date)).days if c.incident_date else 5
    cands = workflows.candidates(domain, (c.claimed_paise or 0) / 100, cov)
    c.ranking = decision.rank(cands, avail, max(0, days))
    c.followup_date = (today() + timedelta(days=wf["followup_days"])).isoformat()
    sup_ratio = (sum(1 for x in claims if x["status"] == "SUPPORTED") / len(claims)) if claims else 0.0
    cov_mean = sum(cov.values()) / max(1, len(cov))
    top_conf = hits[0]["evidence_scores"]["confidence"] if hits else 0.0
    conf = round(0.5 * cov_mean + 0.3 * sup_ratio + 0.2 * top_conf, 2)
    est = [d for d in docs if d.doc_type]
    tl = [{"date": c.incident_date, "event": "Incident date (from your text/documents)"}] if c.incident_date else []
    tl += [{"date": x["iso"], "event": "Date mentioned: " + x["text"]} for x in ents["dates"][1:6]]
    c.analysis = {
        "summary": c.description[:400], "issue_type": c.issue_type, "timeline": sorted(tl, key=lambda x: x["date"] or ""),
        "established_facts": [x for x in claims if x["status"] == "SUPPORTED"], "uncertain_claims": [x for x in claims if x["status"] != "SUPPORTED"],
        "basis": [{"id": h["id"], "title": h["title"], "authority": h["authority"], "provenance": h["provenance"], "source_url": h["source_url"], "confidence": h["evidence_scores"]["confidence"],
                   "passage": h["passage"]} for h in hits[:3]],
        "basis_note": ("No retrieved source supports a legal basis for this domain yet; none is asserted." if not hits else
                       "Passages are retrieved from the knowledge base with provenance; 'authored_guide' means written by RECLAIM's authors, not an official text. Verify against the official source."),
        "remedies": workflows.handoff_steps(domain), "missing_evidence": [x["label"] for x in chk if not x["covered"]],
        "recommended": c.ranking.get("optimal"), "alternatives": [r["key"] for r in c.ranking.get("ranked", [])[1:]],
        "risks": [f"Contradicted claim: {x['claim']}" for x in claims if x["status"] == "CONTRADICTED"] + [f"Missing: {x['label']}" for x in chk if not x["covered"]],
        "effort_time": "Direct step ~1 week, escalation ~2 weeks, regulatory 1-2 months (stage defaults, assumptions)",
        "confidence": conf, "confidence_explanation": f"0.5 x evidence coverage {cov_mean:.2f} + 0.3 x supported claims {sup_ratio:.2f} + 0.2 x top source confidence {top_conf:.2f}",
        "followup_date": c.followup_date, "approval_required": True,
        "documents_considered": len(est), "healthcare_note": "Administrative support only. REDEEM does not diagnose, prescribe or give medical advice." if domain == "healthcare" else None}
    set_stage(db, c, "ANALYZED", {"confidence": conf})
    set_stage(db, c, "ACTIONS_RANKED", {"optimal": c.ranking.get("optimal"), "options": len(c.ranking.get("ranked", []))})
    if not miss:
        _ensure_draft(db, c, hits, docs)
        if c.stage not in ("APPROVED", "SUBMITTED", "TRACKING") and c.status not in ("SUBMITTED", "TRACKING", "RESOLVED", "UNRESOLVED", "CLOSED"):
            c.status = "AWAITING_APPROVAL"
            set_stage(db, c, "AWAITING_APPROVAL")


def _body(db: Session, c: Case, hits: list[dict], docs: list[Document]) -> str:
    case = {"intake": {k: v for k, v in (c.intake or {}).items() if not k.startswith("_")}, "documents": [{"filename": d.filename, "doc_type": d.doc_type, "sha256": d.sha256} for d in docs],
            "issue_type": c.issue_type, "provider": c.provider, "description": c.description, "user_name": (c.intake or {}).get("_user_name") or "[Your name]"}
    return workflows.draft(c.domain, case, hits)


def _ensure_draft(db: Session, c: Case, hits: list[dict], docs: list[Document]) -> CaseDraft:
    latest = db.scalar(select(CaseDraft).where(CaseDraft.case_id == c.id).order_by(CaseDraft.version.desc()))
    body = _body(db, c, hits, docs)
    h = hashlib.sha256(body.encode()).hexdigest()
    if latest and (latest.origin == "user_edit" or latest.status in ("APPROVED", "SUBMITTED") or latest.content_hash == h):
        return latest  # never overwrite a user's edit or an approved/submitted draft
    cited = kb.assert_cited(body, [x["id"] for x in hits])
    if latest:
        latest.status = "SUPERSEDED"
    d = CaseDraft(tenant_id=c.tenant_id, case_id=c.id, version=(latest.version + 1) if latest else 1, body=body, content_hash=h, cited=cited)
    db.add(d)
    db.flush()
    set_stage(db, c, "DRAFTED", {"version": d.version, "cited": cited})
    return d


# ---------------------------------------------------------------- user-facing operations
def update_intake(db: Session, c: Case, fields: dict[str, str]) -> None:
    prof = profiles.profile(c.domain)
    for k, v in fields.items():
        if k in prof["evidence_schema"] or k in ("issue_type", "order_id", "policy_number", "claim_number", "complaint_reference", "pnr"):
            c.intake = {**(c.intake or {}), k: str(v)[:300]}
    log(db, c, "INTAKE_UPDATED", {"fields": list(fields)})
    _invalidate_approval(db, c, "intake changed")
    run_pipeline(db, c)


def attach_document(db: Session, c: Case, doc: Document) -> None:
    doc.case_id, doc.domain = c.id, c.domain
    chk = workflows.WF[c.domain]["checklist"]
    doc.relevance = profiles.relevance(doc.text_content or "", c.domain, doc.filename) if doc.text_content else doc.relevance
    from .docintel import strength
    doc.strength = strength(doc.doc_type or "other", doc.relevance or {}, (doc.fields or {}).get("facts", []), chk)
    log(db, c, "DOCUMENT_ATTACHED", {"document_id": doc.id, "filename": doc.filename, "doc_type": doc.doc_type, "relevant": (doc.relevance or {}).get("relevant"), "strength": doc.strength.get("score")})
    run_pipeline(db, c)


def detach_document(db: Session, c: Case, doc: Document) -> None:
    doc.case_id = None
    log(db, c, "DOCUMENT_DETACHED", {"document_id": doc.id})
    run_pipeline(db, c)


def edit_draft(db: Session, c: Case, body: str) -> CaseDraft:
    if c.status in ("SUBMITTED", "TRACKING", "RESOLVED", "UNRESOLVED", "CLOSED"):
        raise CaseError(409, "case_locked", "This case was already submitted; start a follow-up case to change the draft.")
    latest = db.scalar(select(CaseDraft).where(CaseDraft.case_id == c.id).order_by(CaseDraft.version.desc()))
    kb.assert_cited(body, [h["id"] for h in c.sources])  # a user may not introduce a citation that was not retrieved
    if latest:
        latest.status = "SUPERSEDED"
    d = CaseDraft(tenant_id=c.tenant_id, case_id=c.id, version=(latest.version if latest else 0) + 1, body=body, origin="user_edit", content_hash=hashlib.sha256(body.encode()).hexdigest(),
                  cited=kb.assert_cited(body, [h["id"] for h in c.sources]))
    db.add(d)
    db.flush()
    log(db, c, "DRAFT_EDITED", {"version": d.version})
    _invalidate_approval(db, c, "draft edited")
    c.status, c.stage = "AWAITING_APPROVAL", "AWAITING_APPROVAL"
    return d


def rerank(db: Session, c: Case, weights: dict | None) -> dict:
    w = decision.Weights(**{k: float(v) for k, v in (weights or {}).items() if k in ("benefit", "cost", "delay", "risk", "privacy")})
    cov = {x["id"]: x["strength"] for x in c.checklist}
    days = (today() - date.fromisoformat(c.incident_date)).days if c.incident_date else 5
    cands = workflows.candidates(c.domain, (c.claimed_paise or 0) / 100, cov)
    c.ranking = decision.rank(cands, {k for k, v in cov.items() if v >= 0.35}, max(0, days), w)
    log(db, c, "ACTIONS_RERANKED", {"weights": c.ranking.get("weights"), "optimal": c.ranking.get("optimal")})
    return c.ranking


def _digest(c: Case, draft: CaseDraft, action_key: str) -> str:
    return hashlib.sha256(canonical([c.id, draft.content_hash, action_key, c.claimed_paise, c.provider, c.domain]).encode()).hexdigest()


def current_draft(db: Session, c: Case) -> CaseDraft | None:
    return db.scalar(select(CaseDraft).where(CaseDraft.case_id == c.id).order_by(CaseDraft.version.desc()))


def _invalidate_approval(db: Session, c: Case, why: str) -> None:
    if c.approval:
        log(db, c, "APPROVAL_INVALIDATED", {"reason": why, "was": c.approval.get("action_key")})
        c.approval = None
        d = current_draft(db, c)
        if d and d.status == "APPROVED":
            d.status = "DRAFT"
        if c.status == "APPROVED":
            c.status = "AWAITING_APPROVAL"


def approve(db: Session, c: Case, user_id: str, action_key: str, digest: str) -> dict:
    d = current_draft(db, c)
    if c.missing or not d:
        raise CaseError(409, "not_ready", "The case still needs information before it can be approved.")
    keys = [r["key"] for r in c.ranking.get("ranked", [])]
    if action_key not in keys:
        raise CaseError(404, "unknown_action", "No such action for this case.")
    expect = _digest(c, d, action_key)
    if digest != expect:
        raise CaseError(409, "digest_mismatch", "The draft or case facts changed since you reviewed them; review again.")
    c.approval = {"action_key": action_key, "digest": expect, "by": user_id, "at": utcnow().isoformat(), "draft_version": d.version}
    c.selected_action = action_key
    d.status = "APPROVED"
    c.status = "APPROVED"
    set_stage(db, c, "APPROVED", {"action": action_key, "draft_version": d.version})
    return c.approval


def submit(db: Session, c: Case) -> dict:
    d = current_draft(db, c)
    if not c.approval or not d or c.approval["digest"] != _digest(c, d, c.approval["action_key"]):
        raise CaseError(409, "approval_required", "A valid approval bound to the current draft is required before submission.")
    conn = CaseDeskConnector(db, c.tenant_id)
    key = f"case:{c.id}:{d.content_hash[:20]}"
    params = {"domain": c.domain, "title": c.title[:190], "body": d.body, "source_ids": d.cited}
    log(db, c, "SUBMIT_DISPATCHING", {"idempotency_key": key})
    db.commit()  # write-ahead
    receipt = conn.submit("prepare_case", params, key)
    result, evidence = conn.verify("prepare_case", params, key, {})
    if result != "VERIFIED":
        log(db, c, "SUBMIT_VERIFICATION_FAILED", evidence)
        raise CaseError(502, "verification_failed", "The record was not found on read-back; nothing is marked submitted.")
    step = next((s for s in workflows.handoff_steps(c.domain) if s["stage"] == c.approval["action_key"].split("_")[0]), workflows.handoff_steps(c.domain)[0])
    c.handoff = {"mode": "guided_handoff", "internal_record": receipt["ref"], "step": step, "readback": evidence,
                 "statement": "Your approved draft is recorded in REDEEM. REDEEM has no verified filing channel to this authority, so nothing has been sent to them; submit it yourself using the links, then log the acknowledgement here.",
                 "documents_to_attach": [x["label"] for x in c.checklist if x["covered"]]}
    d.status = "SUBMITTED"
    c.status = "SUBMITTED"
    set_stage(db, c, "SUBMITTED", {"internal_record": receipt["ref"], "external_filing": False})
    return c.handoff


def track(db: Session, c: Case, kind: str, reference: str | None, note: str, doc: Document | None, amount_paise: int | None) -> None:
    if c.status not in ("SUBMITTED", "TRACKING", "RESOLVED", "UNRESOLVED"):
        raise CaseError(409, "not_submitted", "Record provider responses after the case has been submitted.")
    if doc:
        attach_document_light(db, c, doc)
    cat = "USER_REPORTED_WITH_DOCUMENT" if doc else "USER_REPORTED"
    log(db, c, "PROVIDER_UPDATE", {"kind": kind, "reference": reference, "note": note[:500], "document_id": doc.id if doc else None, "evidence_category": cat, "amount_paise": amount_paise})
    if kind in ("acknowledgement", "response", "escalated"):
        c.status = "TRACKING"
        set_stage(db, c, "TRACKING", {"kind": kind})
    elif kind in ("resolved", "rejected"):
        verified = bool(doc and (doc.relevance or {}).get("relevant"))
        c.status = "RESOLVED" if kind == "resolved" else "UNRESOLVED"
        c.outcome = {"kind": kind, "amount_paise": amount_paise, "reference": reference, "note": note[:500], "evidence_category": cat,
                     "verification": "SUPPORTED_BY_DOCUMENT" if verified else "USER_REPORTED_UNVERIFIED",
                     "statement": "Outcome is supported by an attached document." if verified else "Outcome is what you told REDEEM; no document confirms it, so it is not verified."}
        set_stage(db, c, "OUTCOME_VERIFIED" if verified else "OUTCOME_REPORTED_UNVERIFIED", {"outcome": kind})


def attach_document_light(db: Session, c: Case, doc: Document) -> None:
    doc.case_id, doc.domain = c.id, c.domain


def close(db: Session, c: Case) -> None:
    c.status = "CLOSED"
    set_stage(db, c, "CLOSED")


def overdue(c: Case) -> bool:
    return bool(c.followup_date and c.status in ("SUBMITTED",) and c.followup_date < today().isoformat())


# ---------------------------------------------------------------- views / reports
def view(db: Session, c: Case) -> dict:
    docs = _docs(db, c)
    d = current_draft(db, c)
    drafts = list(db.scalars(select(CaseDraft).where(CaseDraft.case_id == c.id).order_by(CaseDraft.version)))
    claims = list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == c.id)))
    key = (c.approval or {}).get("action_key") or c.ranking.get("optimal")
    return {
        "id": c.id, "mission_id": c.mission_id, "domain": c.domain, "domain_label": profiles.LABEL[c.domain], "issue_type": c.issue_type, "title": c.title, "description": c.description,
        "provider": c.provider, "stage": c.stage, "stages": STAGES, "status": c.status, "intake": {k: v for k, v in (c.intake or {}).items() if not k.startswith("_")},
        "schema": profiles.profile(c.domain)["evidence_schema"], "critical": workflows.WF[c.domain]["critical"], "entities": c.entities, "missing": c.missing,
        "checklist": c.checklist, "sources": c.sources, "analysis": c.analysis, "ranking": c.ranking, "selected_action": c.selected_action, "approval": c.approval,
        "approval_valid": bool(c.approval and d and c.approval["digest"] == _digest(c, d, c.approval["action_key"])), "handoff": c.handoff, "outcome": c.outcome,
        "claimed_paise": c.claimed_paise, "incident_date": c.incident_date, "followup_date": c.followup_date, "overdue": overdue(c), "assumption_note": "Stage durations, risk and privacy values are heuristic defaults, not predictions.",
        "draft": ({"version": d.version, "body": d.body, "status": d.status, "origin": d.origin, "cited": d.cited, "content_hash": d.content_hash,
                   "approval_digest": _digest(c, d, key) if key else None, "approval_action": key} if d else None),
        "drafts": [{"version": x.version, "status": x.status, "origin": x.origin, "hash": x.content_hash[:12], "created_at": x.created_at.isoformat()} for x in drafts],
        "documents": [{"id": x.id, "filename": x.filename, "doc_type": x.doc_type, "version": x.version, "sha256": x.sha256, "strength": x.strength, "relevance": x.relevance, "ocr_status": x.ocr_status,
                       "facts": (x.fields or {}).get("facts", [])[:30], "near_duplicate_of": (x.fields or {}).get("near_duplicate_of"), "supersedes": x.supersedes, "page_count": x.page_count} for x in docs],
        "claims": [{"field": x.field, "claim": x.claim, "status": x.status, "support": x.support} for x in claims],
        "events": [{"seq": e.seq, "type": e.type, "data": e.data, "at": e.created_at.isoformat()} for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.seq))],
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


def report(db: Session, c: Case) -> dict:
    v = view(db, c)
    return {"case": {k: v[k] for k in ("id", "title", "domain_label", "status", "stage", "provider", "issue_type", "incident_date", "followup_date", "claimed_paise")},
            "problem_summary": v["analysis"].get("summary"), "timeline": v["analysis"].get("timeline"), "established_facts": v["analysis"].get("established_facts"),
            "uncertain_claims": v["analysis"].get("uncertain_claims"), "basis": v["analysis"].get("basis"), "basis_note": v["analysis"].get("basis_note"),
            "evidence": [{"filename": d["filename"], "type": d["doc_type"], "strength": d["strength"].get("score"), "sha256": d["sha256"]} for d in v["documents"]],
            "missing_evidence": v["analysis"].get("missing_evidence"), "recommended_action": v["analysis"].get("recommended"), "alternatives": v["analysis"].get("alternatives"),
            "confidence": v["analysis"].get("confidence"), "confidence_explanation": v["analysis"].get("confidence_explanation"), "draft": v["draft"], "approval": v["approval"], "handoff": v["handoff"],
            "outcome": v["outcome"], "provenance_note": "Evidence categories: USER_REPORTED, document-backed claims, KB passages (scraped_official / authored_guide). No filing is made by REDEEM.",
            "events": v["events"], "generated_at": utcnow().isoformat()}


def to_markdown(r: dict) -> str:
    c = r["case"]
    L = [f"# Case report — {c['title']}", "", f"- Case `{c['id']}` · {c['domain_label']} · status **{c['status']}** (stage {c['stage']})",
         f"- Provider: {c['provider'] or 'n/a'} · Issue: {c['issue_type']} · Incident: {c['incident_date'] or 'n/a'} · Follow-up: {c['followup_date'] or 'n/a'}", "", "## Problem", r["problem_summary"] or "", "", "## Established facts (document-backed)"]
    L += [f"- {x['claim']}" for x in r["established_facts"] or []] or ["- none"]
    L += ["", "## Uncertain or unsupported claims"] + ([f"- {x['claim']} — {x['status']}" for x in r["uncertain_claims"] or []] or ["- none"])
    L += ["", "## Possible basis (retrieved passages)", r["basis_note"] or ""]
    L += [f"- [{b['id']}] {b['title']} — {b['authority'] or 'unknown'} ({b['provenance']}, confidence {b['confidence']})" for b in r["basis"] or []]
    L += ["", "## Evidence"] + ([f"- {e['filename']} ({e['type']}, strength {e['strength']}, sha256 {e['sha256'][:12]}…)" for e in r["evidence"]] or ["- none attached"])
    L += ["", "## Missing evidence"] + ([f"- {m}" for m in r["missing_evidence"] or []] or ["- none"])
    L += ["", f"## Recommendation: {r['recommended_action']}  (confidence {r['confidence']})", r["confidence_explanation"] or ""]
    if r["handoff"]:
        L += ["", "## Handoff", r["handoff"]["statement"]]
    if r["outcome"]:
        L += ["", "## Outcome", f"{r['outcome']['kind']} — {r['outcome']['statement']}"]
    return "\n".join(L) + "\n"


def bundle(db: Session, c: Case) -> bytes:
    r = report(db, c)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.json", json.dumps(r, indent=1, ensure_ascii=False, default=str))
        z.writestr("report.md", to_markdown(r))
        for d in db.scalars(select(CaseDraft).where(CaseDraft.case_id == c.id)):
            z.writestr(f"drafts/v{d.version}-{d.status.lower()}.txt", d.body)
        z.writestr("sources.json", json.dumps(c.sources, indent=1, ensure_ascii=False))
        for d in _docs(db, c):
            if d.blob_path:
                try:
                    z.write(d.blob_path, f"evidence/{d.filename}")
                except OSError:
                    z.writestr(f"evidence/{d.filename}.MISSING.txt", "file bytes unavailable")
    return buf.getvalue()


def mark_from_mission(db: Session, case_id: str, tenant_id: str, user_id: str, mission_id: str, ref: str, evidence: dict, mode: str) -> None:
    """A mission action was independently verified: reflect it on the case (mode = 'guided_handoff' | 'fixture_provider_request')."""
    c = db.scalar(select(Case).where(Case.id == case_id, Case.tenant_id == tenant_id))
    if not c:
        return
    d = current_draft(db, c)
    c.approval = {"action_key": "mission_action", "by": user_id, "via_mission": mission_id, "at": utcnow().isoformat(), "digest": None, "draft_version": d.version if d else None}
    if mode == "guided_handoff":
        step = workflows.handoff_steps(c.domain)[0]
        c.handoff = {"mode": mode, "internal_record": ref, "step": step, "readback": evidence, "via_mission": mission_id,
                     "statement": "Your approved draft is recorded in REDEEM through the mission. REDEEM has no verified filing channel to this authority, so nothing has been sent to them; submit it yourself using the links.",
                     "documents_to_attach": [x["label"] for x in c.checklist if x["covered"]]}
        if d:
            d.status = "SUBMITTED"
    else:
        c.handoff = {"mode": mode, "internal_record": ref, "readback": evidence, "via_mission": mission_id,
                     "statement": "The request was sent to a LOCAL FIXTURE airline desk and read back independently. No real airline was contacted."}
    c.status = "SUBMITTED"
    set_stage(db, c, "SUBMITTED", {"via_mission": mission_id, "mode": mode, "external_filing": False})
