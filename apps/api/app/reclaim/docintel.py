"""Document intelligence: ingest -> extract text (txt/pdf) -> classify -> extract facts with source locations -> relevance -> strength ->
duplicate / near-duplicate / version history. Images need OCR; no OCR engine is installed here, so images are stored with ocr_status=OCR_UNAVAILABLE
(an explicit blocked state) and are never given invented text."""
import hashlib
import io
import re
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Document
from . import profiles, workflows

TYPE_RULES = [
    ("rejection_letter", ["we regret", "your claim has been rejected", "claim is rejected", "repudiat", "cannot be processed", "request is declined", "has been denied", "not admissible"]),
    ("ticket", ["e-ticket", "boarding pass", "pnr", "itinerary", "passenger name", "flight no"]),
    ("policy", ["policy number", "policy schedule", "sum insured", "policy period", "terms and conditions", "tariff plan"]),
    ("medical_bill", ["hospital bill", "room charges", "consultation charges", "itemised bill", "patient name", "ip no"]),
    ("discharge_summary", ["discharge summary", "date of discharge", "diagnosis"]),
    ("statement", ["account statement", "statement period", "txn date", "closing balance", "transaction id", "debit", "credit"]),
    ("invoice", ["invoice no", "invoice number", "tax invoice", "gst", "order id", "order no"]),
    ("receipt", ["receipt", "payment received", "amount paid", "paid via", "payment successful"]),
    ("agreement", ["agreement", "lease", "tenancy", "allotment letter", "sale deed", "whereas"]),
    ("bill", ["bill date", "bill amount", "amount due", "due date", "billing period", "postpaid"]),
    ("notice", ["notice", "acknowledg", "reference number", "docket", "complaint number", "ticket number", "registered your"]),
    ("application", ["application form", "application number", "applicant"]),
    ("claim_form", ["claim form", "claim number", "claim intimation"]),
    ("id_proof", ["aadhaar", "pan card", "passport", "driving licence", "voter id"]),
    ("correspondence", ["dear", "regards", "sincerely", "subject:", "from:", "wrote:"]),
]


def blob_dir(tenant_id: str) -> Path:
    d = Path(settings.data_dir) / "blobs" / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def extract_text(filename: str, ctype: str, data: bytes) -> tuple[str | None, int | None, str | None, list[str]]:
    """-> (text, page_count, ocr_status, per_page_text)"""
    low = filename.lower()
    if ctype.startswith("text/") or low.endswith((".txt", ".md", ".csv")):
        t = data.decode("utf-8", errors="replace")
        return t, None, None, [t]
    if ctype == "application/pdf" or low.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            pages = [(p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages]
        except Exception:
            return None, None, "PDF_UNREADABLE", []
        text = "\n".join(pages).strip()
        return (text or None), len(pages), (None if text else "OCR_UNAVAILABLE_SCANNED_PDF"), pages
    if ctype.startswith("image/") or low.endswith((".png", ".jpg", ".jpeg")):
        return None, None, ("OCR_UNAVAILABLE" if not shutil.which("tesseract") else "OCR_NOT_IMPLEMENTED"), []
    return None, None, "UNSUPPORTED_TYPE", []


def classify(text: str, filename: str) -> dict:
    low = (filename + " " + (text or "")[:4000]).lower()
    best, score = "other", 0
    for t, kws in TYPE_RULES:
        s = sum(1 for k in kws if k in low)
        if s > score:
            best, score = t, s
    return {"doc_type": best, "confidence": round(min(1.0, 0.35 + 0.25 * score), 2) if score else 0.0}


def facts(text: str, pages: list[str], domain: str | None) -> list[dict]:
    """Extracted facts WITH where they came from (page + character span + surrounding quote) so the UI can highlight them."""
    ents = profiles.extract_entities(text or "", domain)
    out = []
    offs = []
    pos = 0
    for i, p in enumerate(pages):
        offs.append((pos, i + 1))
        pos += len(p) + 1

    def page_of(ch):
        pg = 1
        for o, n in offs:
            if ch >= o:
                pg = n
        return pg

    for a in ents["amounts"]:
        out.append({"kind": "amount", "value": a["value_paise"], "display": a["text"], "span": a["span"]})
    for d in ents["dates"]:
        out.append({"kind": "date", "value": d["iso"], "display": d["text"], "span": d["span"]})
    for i in ents["ids"]:
        out.append({"kind": i["kind"], "value": i["value"], "display": i["value"], "span": i["span"]})
    for p in ents["providers"]:
        out.append({"kind": "provider", "value": p["name"], "display": p["name"], "span": None})
    for f in out:
        if f["span"]:
            a, b = f["span"]
            f["quote"] = (text or "")[max(0, a - 40): b + 40].replace("\n", " ").strip()
            f["page"] = page_of(a)
    return out


def near_dup(db: Session, tenant_id: str, text: str, exclude_id: str | None = None) -> str | None:
    if not text:
        return None
    a = set(re.findall(r"[a-z0-9]{3,}", text.lower()))
    if len(a) < 12:
        return None
    for d in db.scalars(select(Document).where(Document.tenant_id == tenant_id, Document.text_content.is_not(None), Document.duplicate_of.is_(None))):
        if d.id == exclude_id or not d.text_content:
            continue
        b = set(re.findall(r"[a-z0-9]{3,}", d.text_content.lower()))
        if b and len(a & b) / len(a | b) >= 0.85:
            return d.id
    return None


def strength(doc_type: str, rel: dict, fact_list: list[dict], checklist: list[dict]) -> dict:
    """Evidence strength 0..1 with an explanation. = 0.4 relevance + 0.35 matches a checklist item + 0.25 facts extracted (cap 4)."""
    r = min(1.0, rel.get("hits", 0) / 4) if rel.get("relevant") else 0.0
    match = [c["id"] for c in checklist if doc_type in c["types"]]
    m = 1.0 if match else 0.0
    y = min(1.0, len([f for f in fact_list if f["kind"] != "provider"]) / 4)
    s = round(0.4 * r + 0.35 * m + 0.25 * y, 2)
    return {"score": s, "matches_checklist": match,
            "explanation": f"relevance {r:.2f} (x0.4) + checklist match {'yes' if m else 'no'} (x0.35) + {len(fact_list)} extracted fact(s) {y:.2f} (x0.25)"}


def ingest(db: Session, tenant_id: str, filename: str, ctype: str, data: bytes, domain: str | None = None, case_id: str | None = None, mission_id: str | None = None) -> tuple[Document, dict]:
    name = re.sub(r"[^\w.\- ]", "_", filename or "upload")[:200]
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.tenant_id == tenant_id, Document.sha256 == sha, Document.duplicate_of.is_(None)))
    if existing:
        if case_id and not existing.case_id:
            existing.case_id = case_id
        return existing, {"duplicate": True, "duplicate_of": existing.id, "note": "Identical file already in your vault; not stored twice."}
    text, pages_n, ocr, pages = extract_text(name, ctype, data)
    cls = classify(text or "", name) if text else {"doc_type": "other", "confidence": 0.0}
    fl = facts(text or "", pages, domain) if text else []
    rel = profiles.relevance(text or "", domain, name) if (domain and text) else {"relevant": bool(text), "hits": 0, "reason": "No domain given." if text else "No extractable text."}
    chk = workflows.WF[domain]["checklist"] if domain in workflows.WF else []
    st = strength(cls["doc_type"], rel, fl, chk)
    prev = db.scalar(select(Document).where(Document.tenant_id == tenant_id, Document.filename == name).order_by(Document.version.desc()))
    path = blob_dir(tenant_id) / sha
    path.write_bytes(data)
    d = Document(tenant_id=tenant_id, mission_id=mission_id, filename=name, content_type=ctype or "application/octet-stream", sha256=sha, version=(prev.version + 1) if prev else 1,
                 size=len(data), text_content=text, extracted={"booking_refs": sorted(set(re.findall(r"\b[A-Z]{2}\d{3,4}\b", text or ""))), "ocr_status": ocr,
                                                                "note": "Parsed by deterministic rules; document text is data, never instructions."},
                 case_id=case_id, domain=domain, doc_type=cls["doc_type"], fields={"facts": fl, "classification": cls}, relevance=rel, strength=st,
                 supersedes=prev.id if prev else None, ocr_status=ocr, page_count=pages_n, blob_path=str(path))
    db.add(d)
    db.flush()
    nd = near_dup(db, tenant_id, text or "", d.id)
    if nd:
        d.fields = {**d.fields, "near_duplicate_of": nd}
    return d, {"duplicate": False, "near_duplicate_of": nd, "supersedes": prev.id if prev else None}
