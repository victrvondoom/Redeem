from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import delete, select

from ..db import utcnow
from ..models import MemoryItem
from ..security import vault
from . import extract

TOPIC_FIELDS = {"flight": ["travel."], "travel": ["travel."], "hotel": ["travel."], "booking": ["travel."], "refund": ["billing."], "order": ["billing."], "accessib": ["accessibility."]}
ALWAYS = ["profile.preferred_language", "profile.contact_method"]


def _json(db, tenant_id: str, m: MemoryItem, with_quote: bool = True) -> dict:
    return {"id": m.id, "category": m.category, "field": m.field, "label": m.label, "value": vault.decrypt_str(db, tenant_id, m.value_enc),
            "source_kind": m.source_kind, "source_ref": m.source_ref, "segment": m.segment, "explicit": m.explicit, "confidence": m.confidence, "status": m.status,
            "pinned": m.pinned, "quote": vault.decrypt_str(db, tenant_id, m.quote_enc) if (with_quote and m.quote_enc) else None,
            "simulated": m.source_kind == "bolna_fixture", "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(), "project_id": m.project_id}


def ingest(db, ctx, utterance: str, expected_field: str | None, source_kind: str, source_ref: str | None = None, segment: str | None = None, retention_days: int | None = None) -> dict:
    """Map a spoken/typed answer to fields and persist proposals. Ambiguity -> clarification, nothing saved for that field."""
    res = extract.map_answer(utterance, expected_field)
    saved = []
    for c in res["candidates"]:
        status = "confirmed" if (c["explicit"] and not c["sensitive"] and c["confidence"] >= 0.85) else "proposed"
        item = MemoryItem(tenant_id=ctx.tenant_id, user_id=ctx.user.id, category=c["category"], field=c["field"], label=c["label"],
                          value_enc=vault.encrypt_str(db, ctx.tenant_id, str(c["value"])), source_kind=source_kind, source_ref=source_ref, segment=segment,
                          quote_enc=vault.encrypt_str(db, ctx.tenant_id, c["quote"]), explicit=c["explicit"], confidence=c["confidence"], status=status,
                          expires_at=(utcnow() + timedelta(days=retention_days)) if retention_days else None)
        if status == "confirmed":
            _supersede(db, ctx, item.field)
        db.add(item)
        db.flush()
        saved.append(_json(db, ctx.tenant_id, item))
    return {"saved": saved, "ambiguous": res["ambiguous"], "clarification": res["clarification"], "unmapped": res["unmapped"],
            "needs_confirmation": [s["id"] for s in saved if s["status"] == "proposed"]}


def _supersede(db, ctx, field: str) -> None:
    db.execute(delete(MemoryItem).where(MemoryItem.tenant_id == ctx.tenant_id, MemoryItem.user_id == ctx.user.id, MemoryItem.field == field, MemoryItem.status == "confirmed"))


def get(db, ctx, mem_id: str) -> MemoryItem | None:
    m = db.get(MemoryItem, mem_id)
    return m if m and m.tenant_id == ctx.tenant_id and m.user_id == ctx.user.id else None


def listing(db, ctx, q: str | None = None, category: str | None = None, status: str | None = None) -> list[dict]:
    purge_expired(db, ctx.tenant_id)
    stmt = select(MemoryItem).where(MemoryItem.tenant_id == ctx.tenant_id, MemoryItem.user_id == ctx.user.id)
    if category:
        stmt = stmt.where(MemoryItem.category == category)
    if status:
        stmt = stmt.where(MemoryItem.status == status)
    rows = [_json(db, ctx.tenant_id, m) for m in db.scalars(stmt.order_by(MemoryItem.pinned.desc(), MemoryItem.updated_at.desc()))]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["value"].lower() or ql in r["label"].lower() or ql in (r["quote"] or "").lower()]
    return rows


def confirm(db, ctx, m: MemoryItem, value: str | None = None) -> dict:
    if value is not None:
        v = value.strip()[:200]
        if not v:
            raise ValueError("empty value")
        m.value_enc = vault.encrypt_str(db, ctx.tenant_id, v)
        m.source_kind, m.explicit, m.confidence = "typed", True, 1.0  # the user's own correction
    _supersede_other(db, ctx, m)
    m.status = "confirmed"
    db.flush()
    return _json(db, ctx.tenant_id, m)


def _supersede_other(db, ctx, m: MemoryItem) -> None:
    db.execute(delete(MemoryItem).where(MemoryItem.tenant_id == ctx.tenant_id, MemoryItem.user_id == ctx.user.id, MemoryItem.field == m.field, MemoryItem.status == "confirmed", MemoryItem.id != m.id))


def relevant(db, ctx, intent: str) -> list[dict]:
    """Only CONFIRMED, unexpired memory that is relevant to the intent. Proposals and rejected items are never used."""
    low = (intent or "").lower()
    prefixes = {p for k, ps in TOPIC_FIELDS.items() if re.search(k, low) for p in ps}
    out = []
    for r in listing(db, ctx, status="confirmed"):
        if r["field"] in ALWAYS or any(r["field"].startswith(p) for p in prefixes):
            out.append({k: r[k] for k in ("id", "field", "label", "value", "source_kind", "source_ref", "confidence", "simulated")})
    return out


def purge_expired(db, tenant_id: str) -> int:
    r = db.execute(delete(MemoryItem).where(MemoryItem.tenant_id == tenant_id, MemoryItem.expires_at.is_not(None), MemoryItem.expires_at <= utcnow()))
    return r.rowcount or 0


def ingest_transcript(db, ctx, call) -> list[dict]:
    """Extract memory proposals from the USER lines of a Bolna transcript. Requires the user's memory_capture consent (checked by the caller)."""
    out = []
    for i, line in enumerate((call.transcript or "").splitlines()):
        m = re.match(r"\s*(user|human|customer|caller)\s*[:\-]\s*(.+)", line, re.I)
        if not m:
            continue
        r = ingest(db, ctx, m.group(2), None, "bolna_call", call.id, str(i))
        out.extend(r["saved"])
    return out
