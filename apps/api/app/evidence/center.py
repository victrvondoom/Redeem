"""Evidence Center: typed, hashed evidence for every mission, with an explicit trust category.

Categories: USER_PROVIDED, PROVIDER_CONFIRMED, DATABASE_VERIFIED, INFERRED (rule-based here; no model is wired in), UNVERIFIED.
Items are derived deterministically from the persisted ledger, so they cannot drift from what actually happened.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import canonical, sha256_hex
from ..models import Action, ActionEvent, Mission, MissionRevision, VerificationClaim

RETENTION = {"policy": "kept until you delete the mission or workspace", "deletable": True}


def _item(m: Mission, category: str, title: str, source: str, source_type: str, ts, content, status: str, action_id: str | None = None) -> dict:
    h = sha256_hex(canonical(content))
    return {"id": "evd_" + sha256_hex(f"{m.id}|{category}|{title}|{h}")[:16], "category": category, "title": title, "source": source,
            "source_type": source_type, "timestamp": ts.isoformat() if ts else None, "mission_id": m.id, "action_id": action_id,
            "content_hash": h, "verification_status": status, "retention": RETENTION, "content": content}


def build(db: Session, m: Mission) -> list[dict]:
    items: list[dict] = []
    for r in db.scalars(select(MissionRevision).where(MissionRevision.mission_id == m.id).order_by(MissionRevision.revision)):
        items.append(_item(m, "USER_PROVIDED", f"Instruction (revision {r.revision})", "user", "text_or_transcript", r.created_at,
                           {"intent": r.intent, "reason": r.reason}, "AS_STATED"))
    evs = list(db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id).order_by(ActionEvent.seq)))
    for e in evs:
        d = e.data
        if e.type == "CLASSIFIED":
            items.append(_item(m, "INFERRED", "Domains and language", "rule-based router", "inference", e.created_at,
                               {"domains": d.get("domains"), "language_detected": d.get("language_detected"), "scenario": d.get("scenario")}, "NOT_INDEPENDENTLY_CONFIRMED"))
        elif e.type == "ENTITY_BOUND":
            user = d.get("via") == "user_selection" or str(d.get("via", "")).startswith("document:") or d.get("via") == "explicit_reference"
            items.append(_item(m, "USER_PROVIDED" if user else "INFERRED", f"Target entity bound ({d.get('role')})", d.get("via", "system"),
                               "entity_binding", e.created_at, {"role": d.get("role"), "id": d.get("id"), "via": d.get("via")},
                               "AS_STATED" if user else "NOT_INDEPENDENTLY_CONFIRMED"))
        elif e.type == "POLICY" and e.action_id:
            items.append(_item(m, "INFERRED", "Safety policy decision", "safety engine (deterministic)", "policy", e.created_at, d, "RULE_EVALUATED", e.action_id))
        elif e.type == "APPROVED":
            items.append(_item(m, "USER_PROVIDED", "Approval", f"user:{d.get('by')}", "approval", e.created_at, d, "AS_STATED", e.action_id))
        elif e.type == "DISPATCHING":
            items.append(_item(m, "USER_PROVIDED", "Execution request (write-ahead)", "executor", "dispatch_record", e.created_at,
                               {"idempotency_key": d.get("idempotency_key")}, "RECORDED", e.action_id))
        elif e.type == "ACKED":
            items.append(_item(m, "PROVIDER_CONFIRMED", "Provider acknowledgement", "provider", "provider_response", e.created_at, d, "ACK_ONLY_NOT_PROOF", e.action_id))
        elif e.type == "RECONCILED_FOUND":
            items.append(_item(m, "PROVIDER_CONFIRMED", "Provider record found by lookup", "provider", "reconciliation", e.created_at, d, "ACK_ONLY_NOT_PROOF", e.action_id))
    for c in db.scalars(select(VerificationClaim).where(VerificationClaim.mission_id == m.id).order_by(VerificationClaim.created_at)):
        ok = c.result == "VERIFIED"
        items.append(_item(m, "DATABASE_VERIFIED" if ok else "UNVERIFIED", c.claim, "independent read-back", "verification_query", c.created_at,
                           c.evidence, "VERIFIED" if ok else "FAILED", c.action_id))
    for a in db.scalars(select(Action).where(Action.mission_id == m.id)):
        if a.status in ("UNCERTAIN", "BLOCKED", "SKIPPED_DEPENDENCY", "REJECTED") and a.revision == m.revision:
            items.append(_item(m, "UNVERIFIED", f"{a.kind}: {a.status}", "executor", "action_state", a.created_at, {"status": a.status}, "UNRESOLVED", a.id))
    return items


def remaining_uncertainty(db: Session, m: Mission) -> list[str]:
    out = [f"{a.kind} is {a.status}" for a in db.scalars(select(Action).where(Action.mission_id == m.id, Action.revision == m.revision))
           if a.status not in ("VERIFIED", "SUPERSEDED")]
    out += [f"{b['kind']}: {b['reason']}" for b in (m.plan or {}).get("blocked", [])]
    return out


def report(db: Session, m: Mission) -> dict:
    items = build(db, m)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    return {"mission": {"id": m.id, "status": m.status, "revision": m.revision, "intent": m.intent, "domains": m.domains,
                        "scenario": m.scenario, "language_selected": m.language_selected, "language_detected": m.language_detected},
            "scope": "Effects are applied to and verified against local stateful fixtures unless a live provider is stated.",
            "evidence_counts": counts, "evidence": items, "remaining_uncertainty": remaining_uncertainty(db, m), "outcome": m.outcome}


def to_markdown(r: dict) -> str:
    m = r["mission"]
    lines = ["# REDEEM mission report", "", f"- Mission: `{m['id']}`  ·  Status: **{m['status']}**  ·  Revision {m['revision']}",
             f"- Instruction: {m['intent']}", f"- Domains: {', '.join(m['domains']) or 'none'}  ·  Language: {m['language_detected']} (selected {m['language_selected']})",
             f"- Scope: {r['scope']}", "", "## Evidence"]
    for i in r["evidence"]:
        lines.append(f"- **{i['category']}** — {i['title']} ({i['source']}, {i['timestamp']}) · status {i['verification_status']} · hash `{i['content_hash'][:12]}`")
    lines += ["", "## Remaining uncertainty"] + ([f"- {u}" for u in r["remaining_uncertainty"]] or ["- none recorded"])
    if r["outcome"]:
        lines += ["", "## Outcome", f"- {r['outcome'].get('headline_en', r['outcome'].get('status'))}", f"- Ledger hash: `{r['outcome'].get('ledger_chain_head', 'n/a')}`"]
    return "\n".join(lines) + "\n"
