"""Context memory (what was said and answered) and the unified per-user history timeline + derived knowledge graph.

Everything is persisted per user/workspace; turn text is envelope-encrypted. The graph is DERIVED at read time from the user's own rows
(no second copy of private data to leak or go stale)."""
from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import delete, func, select

from ..db import utcnow
from ..models import (ActionEvent, AuditEvent, Call, Case, ConversationTurn, Document, FxBooking, MemoryItem, Mission)
from ..security import vault

FOLLOWUP = re.compile(r"^\s*(also|and|same|that|it|again|what about|then|और|वही|उसी|अब)\b", re.I)
REF = re.compile(r"\b[A-Z]{2}\d{3,4}\b")


def record(db, ctx, channel: str, role: str, text: str, ref_id: str | None = None, idx: int = 0) -> bool:
    """Idempotent per (channel, ref, idx) when idx > 0 (transcript lines); single turns use a fresh idx."""
    text = (text or "").strip()[:4000]
    if not text:
        return False
    if idx == 0:
        idx = (db.scalar(select(func.coalesce(func.max(ConversationTurn.idx), 0)).where(ConversationTurn.tenant_id == ctx.tenant_id, ConversationTurn.channel == channel,
                                                                                   ConversationTurn.ref_id == ref_id)) or 0) + 1
    elif db.scalar(select(ConversationTurn.id).where(ConversationTurn.tenant_id == ctx.tenant_id, ConversationTurn.channel == channel, ConversationTurn.ref_id == ref_id, ConversationTurn.idx == idx)):
        return False
    db.add(ConversationTurn(tenant_id=ctx.tenant_id, user_id=ctx.user.id, channel=channel, ref_id=ref_id, idx=idx, role=role, text_enc=vault.encrypt_str(db, ctx.tenant_id, text)))
    db.flush()
    return True


def _turn_json(db, tenant_id: str, t: ConversationTurn) -> dict:
    return {"id": t.id, "channel": t.channel, "ref_id": t.ref_id, "role": t.role, "text": vault.decrypt_str(db, tenant_id, t.text_enc), "at": t.created_at.isoformat()}


def recent(db, ctx, limit: int = 20, channel: str | None = None, ref_id: str | None = None) -> list[dict]:
    stmt = select(ConversationTurn).where(ConversationTurn.tenant_id == ctx.tenant_id, ConversationTurn.user_id == ctx.user.id)
    if channel:
        stmt = stmt.where(ConversationTurn.channel == channel)
    if ref_id:
        stmt = stmt.where(ConversationTurn.ref_id == ref_id)
    rows = list(db.scalars(stmt.order_by(ConversationTurn.created_at.desc(), ConversationTurn.idx.desc()).limit(limit)))
    return [_turn_json(db, ctx.tenant_id, t) for t in reversed(rows)]


def forget(db, ctx, ref_id: str | None = None) -> int:
    stmt = delete(ConversationTurn).where(ConversationTurn.tenant_id == ctx.tenant_id, ConversationTurn.user_id == ctx.user.id)
    if ref_id:
        stmt = stmt.where(ConversationTurn.ref_id == ref_id)
    return db.execute(stmt).rowcount or 0


def resolve_followup(db, ctx, intent: str, exclude_id: str | None = None) -> Mission | None:
    """A short follow-up ("also move the hotel", "same booking again") inherits the entities bound in this user's most recent mission (<24h).
    Anything that names its own booking reference is NOT a follow-up."""
    if len(intent) > 80 or REF.search(intent) or not FOLLOWUP.search(intent):
        return None
    prev = db.scalar(select(Mission).where(Mission.tenant_id == ctx.tenant_id, Mission.user_id == ctx.user.id, Mission.created_at >= utcnow() - timedelta(hours=24), Mission.id != (exclude_id or "")).order_by(Mission.created_at.desc()))
    return prev if prev and prev.bindings else None


# ---------------------------------------------------------------- unified history timeline
def timeline(db, ctx, kind: str | None = None, q: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    t, u = ctx.tenant_id, ctx.user.id
    items: list[dict] = []
    want = lambda k: not kind or kind == k  # noqa: E731
    if want("mission"):
        for m in db.scalars(select(Mission).where(Mission.tenant_id == t, Mission.user_id == u)):
            items.append({"at": m.created_at, "kind": "mission", "title": m.intent[:140], "detail": m.status, "href": f"/app/missions/{m.id}", "ref": m.id})
    if want("case"):
        for c in db.scalars(select(Case).where(Case.tenant_id == t)):
            items.append({"at": c.created_at, "kind": "case", "title": c.title, "detail": f"{c.domain} · {c.status}", "href": f"/app/cases/{c.id}", "ref": c.id})
    if want("call"):
        for c in db.scalars(select(Call).where(Call.tenant_id == t, Call.user_id == u)):
            items.append({"at": c.created_at, "kind": "call", "title": f"Bolna {c.kind} call", "detail": c.status, "href": "/app/voice", "ref": c.id})
    if want("document"):
        for d in db.scalars(select(Document).where(Document.tenant_id == t)):
            items.append({"at": d.created_at, "kind": "document", "title": d.filename, "detail": f"{d.doc_type or 'file'} v{d.version}", "href": "/app/vault", "ref": d.id})
    if want("memory"):
        for m in db.scalars(select(MemoryItem).where(MemoryItem.tenant_id == t, MemoryItem.user_id == u)):
            items.append({"at": m.updated_at, "kind": "memory", "title": f"{m.label}: {vault.decrypt_str(db, t, m.value_enc)}", "detail": f"{m.status} · {m.source_kind}", "href": "/app/memory", "ref": m.id})
    if want("conversation"):
        for x in db.scalars(select(ConversationTurn).where(ConversationTurn.tenant_id == t, ConversationTurn.user_id == u)):
            items.append({"at": x.created_at, "kind": "conversation", "title": vault.decrypt_str(db, t, x.text_enc)[:160], "detail": f"{x.channel} · {x.role}", "href": f"/app/missions/{x.ref_id}" if x.channel == "mission" and x.ref_id else "/app/memory", "ref": x.id})
    if want("activity"):
        for a in db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == t, AuditEvent.user_id == u)):
            items.append({"at": a.created_at, "kind": "activity", "title": a.action, "detail": a.target or "", "href": "/app/settings", "ref": a.id})
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["title"].lower() or ql in i["detail"].lower()]
    items.sort(key=lambda i: i["at"], reverse=True)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["kind"]] = counts.get(i["kind"], 0) + 1
    page = items[offset: offset + limit]
    for i in page:
        i["at"] = i["at"].isoformat()
    return {"total": len(items), "counts": counts, "items": page}


# ---------------------------------------------------------------- derived knowledge graph
def graph(db, ctx) -> dict:
    t, u = ctx.tenant_id, ctx.user.id
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(i: str, kind: str, label: str, **extra):
        nodes.setdefault(i, {"id": i, "kind": kind, "label": label[:60], **extra})

    def edge(a: str, b: str, rel: str):
        if a in nodes and b in nodes and not any(e["source"] == a and e["target"] == b and e["rel"] == rel for e in edges):
            edges.append({"source": a, "target": b, "rel": rel})

    node("me", "user", ctx.user.name or "You")
    for m in db.scalars(select(MemoryItem).where(MemoryItem.tenant_id == t, MemoryItem.user_id == u, MemoryItem.status != "rejected")):
        v = vault.decrypt_str(db, t, m.value_enc)
        node(f"mem:{m.id}", "memory", f"{m.label}: {v}", status=m.status)
        edge("me", f"mem:{m.id}", "prefers" if m.category in ("travel", "profile", "billing") else "has")
        if m.source_kind == "bolna_call" and m.source_ref:
            node(f"call:{m.source_ref}", "call", "Bolna call")
            edge(f"call:{m.source_ref}", f"mem:{m.id}", "said")
    for c in db.scalars(select(Call).where(Call.tenant_id == t, Call.user_id == u)):
        node(f"call:{c.id}", "call", f"Bolna call ({c.status})")
        edge("me", f"call:{c.id}", "made")
    used: dict[str, list[str]] = {}
    for ev in db.scalars(select(ActionEvent).where(ActionEvent.type == "MEMORY_USED", ActionEvent.mission_id.in_(select(Mission.id).where(Mission.tenant_id == t, Mission.user_id == u)))):
        used.setdefault(ev.mission_id, []).extend(i["id"] for i in (ev.data or {}).get("items", []))
    for m in db.scalars(select(Mission).where(Mission.tenant_id == t, Mission.user_id == u)):
        node(f"mis:{m.id}", "mission", m.intent, status=m.status)
        edge("me", f"mis:{m.id}", "requested")
        for role, eid in (m.bindings or {}).items():
            if role == "booking_id":
                b = db.get(FxBooking, eid)
                if b and b.tenant_id == t:
                    node(f"ent:{b.id}", "entity", f"Booking {b.ref}")
                    edge(f"mis:{m.id}", f"ent:{b.id}", "involves")
        for mid in used.get(m.id, []):
            edge(f"mis:{m.id}", f"mem:{mid}", "used memory")
    for c in db.scalars(select(Case).where(Case.tenant_id == t)):
        node(f"case:{c.id}", "case", c.title, status=c.status)
        node(f"dom:{c.domain}", "domain", c.domain.replace("_", " "))
        edge(f"case:{c.id}", f"dom:{c.domain}", "in domain")
        edge("me", f"case:{c.id}", "opened")
        if c.mission_id:
            edge(f"mis:{c.mission_id}", f"case:{c.id}", "opened case")
    for d in db.scalars(select(Document).where(Document.tenant_id == t)):
        node(f"doc:{d.id}", "document", d.filename)
        edge("me", f"doc:{d.id}", "uploaded")
        if d.case_id:
            edge(f"doc:{d.id}", f"case:{d.case_id}", "supports")
    return {"nodes": list(nodes.values()), "edges": edges, "note": "Derived live from your own records; nothing here is stored separately."}
