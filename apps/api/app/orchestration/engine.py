"""Mission kernel: typed state machine, digest-bound approvals, append-only ledger,
dispatch / reconcile / independent verification.

Deterministic code owns permissions, identity, money, transitions and idempotency. Nothing here
trusts a provider's own acknowledgement as proof of an outcome.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..connectors.base import ProviderRejected, ProviderTimeout, canonical, sha256_hex
from ..connectors.booking import BookingConnector
from ..connectors.calendar import CalendarConnector
from ..connectors.casedesk import CaseDeskConnector
from ..connectors.crm import CrmConnector
from ..connectors.retail import RetailConnector
from ..db import utcnow
from ..domains.language import detect_language, route_domains
from ..fixtures.seed import POLICY_DOCS
from ..models import (Action, ActionApproval, ActionEvent, Connection, FxBooking, FxCustomer, FxLead, FxProduct,
                      Mission, MissionRevision, ProviderOperation, RegSource, VerificationClaim)
from ..policy import citations as cite
from ..policy import safety

IST = timezone(timedelta(hours=5, minutes=30))

TERMINAL = {"VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "CANCELLED", "SUPERSEDED"}
TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"INTENT_CAPTURED"},
    "INTENT_CAPTURED": {"CLASSIFIED", "FAILED", "CANCELLED"},
    "CLASSIFIED": {"DISCOVERING", "FAILED", "CANCELLED"},
    "DISCOVERING": {"ENTITIES_BOUND", "FAILED", "CANCELLED"},
    "ENTITIES_BOUND": {"PLAN_READY", "FAILED", "CANCELLED"},
    "PLAN_READY": {"NEEDS_APPROVAL", "FAILED", "CANCELLED"},
    "NEEDS_APPROVAL": {"AUTHORIZED", "CANCELLED", "FAILED"},
    "AUTHORIZED": {"EXECUTING", "NEEDS_APPROVAL", "CANCELLED"},
    "EXECUTING": {"OBSERVING", "UNCERTAIN", "FAILED", "NEEDS_APPROVAL"},
    "OBSERVING": {"VERIFIED", "PARTIALLY_VERIFIED", "UNCERTAIN", "FAILED"},
    "UNCERTAIN": {"OBSERVING", "FAILED", "CANCELLED"},
}


ABLATIONS: set[str] = set()  # benchmark-only; honoured solely when REDEEM_EVAL_MODE=1


def _ablated(name: str) -> bool:
    return settings.eval_mode and name in ABLATIONS


class EngineError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


# ---------------------------------------------------------------- ledger helpers

def emit(db: Session, m: Mission, type_: str, data: dict | None = None, action_id: str | None = None) -> None:
    db.add(ActionEvent(tenant_id=m.tenant_id, mission_id=m.id, action_id=action_id, type=type_,
                       data=data or {}))
    db.flush()


def transition(db: Session, m: Mission, new: str, reason: str = "") -> None:
    if new == m.status:
        return
    if new not in TRANSITIONS.get(m.status, set()):
        raise EngineError(409, "illegal_transition", f"{m.status} -> {new} is not allowed")
    old, m.status = m.status, new
    emit(db, m, "STATE", {"from": old, "to": new, "reason": reason, "revision": m.revision})


def connector_for(name: str, db: Session, tenant_id: str):
    return {"booking_fixture": BookingConnector, "retail_fixture": RetailConnector, "calendar_fixture": CalendarConnector,
            "crm_fixture": CrmConnector, "casedesk_fixture": CaseDeskConnector}[name](db, tenant_id)


def connection_active(db: Session, tenant_id: str, provider: str) -> bool:
    c = db.scalar(select(Connection).where(Connection.tenant_id == tenant_id, Connection.provider == provider))
    return bool(c and c.status == "active")


def compute_digest(m: Mission, a: Action, version_hash: str) -> str:
    return sha256_hex(canonical({
        "mission": m.id, "tenant": m.tenant_id, "revision": a.revision, "action": a.id, "kind": a.kind,
        "target": a.target_entity_id, "params": a.params, "amount_paise": a.amount_paise,
        "version_hash": version_hash}))


def op_key(m: Mission, kind: str, target: str, params: dict) -> str:
    # Stable across revisions for the *same* logical operation, so a provider can dedupe it.
    return "op_" + sha256_hex(canonical([m.id, kind, target, params]))[:32]


# ---------------------------------------------------------------- pipeline

CASE_DOMAINS = ['telecom', 'housing', 'government', 'healthcare', 'insurance', 'ecommerce', 'consumer_rights', 'banking']
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            "सोमवार": 0, "शनिवार": 5, "रविवार": 6, "சனி": 5, "శని": 5, "திங்கள்": 0, "సోమ": 0}


NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "एक": 1, "दो": 2, "तीन": 3}


def parse_qty(text: str) -> int | None:
    low = text.lower()
    m = re.search(r"\b(\d{1,2})\s*(x|units?|pcs|pieces)?\s*(keyboards?|mouse|mice)\b", low)
    if m:
        return max(1, min(int(m.group(1)), 20))
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\s+(keyboards?|mouse|mice)\b", low) or f"{w} कीबोर्ड" in low:
            return n
    return None


def parse_pickup_date(text: str, now: datetime | None = None) -> str | None:
    low = text.lower()
    today = (now or utcnow()).astimezone(IST).date()
    if "tomorrow" in low:
        return (today + timedelta(days=1)).isoformat()
    for word, wd in WEEKDAYS.items():
        if word in low:
            delta = (wd - today.weekday()) % 7 or 7
            return (today + timedelta(days=delta)).isoformat()
    return None


def start_mission(db: Session, m: Mission, transcript_confidence: float | None = None) -> None:
    """Called once after creation."""
    db.add(MissionRevision(tenant_id=m.tenant_id, mission_id=m.id, revision=1, intent=m.intent,
                           reason="created", bindings={}))
    emit(db, m, "INTENT_CAPTURED", {"intent": m.intent, "source": m.source})
    transition(db, m, "INTENT_CAPTURED", "created")
    advance(db, m, transcript_confidence=transcript_confidence)


def advance(db: Session, m: Mission, confirmed_low_confidence: bool = False,
            transcript_confidence: float | None = None) -> None:
    if m.status != "INTENT_CAPTURED":
        return
    if (m.source == "voice" and transcript_confidence is not None and transcript_confidence < 0.6
            and not confirmed_low_confidence):
        m.clarification = {"type": "low_confidence", "message": "I may have misheard. Please confirm or edit "
                           "what you said before I plan anything.", "transcript": m.intent,
                           "confidence": transcript_confidence}
        emit(db, m, "CLARIFICATION", m.clarification)
        return
    lang = detect_language(m.intent)
    m.language_detected = lang.code
    domains, conf = route_domains(m.intent)
    m.domains = domains
    decision = safety.evaluate_intent(m.intent)
    emit(db, m, "POLICY", decision.as_dict())
    if decision.decision == "REFUSE":
        m.clarification = {"type": "refused", "message": decision.explanation}
        m.outcome = {"status": "FAILED", "reason": "policy_refused", "risk_class": decision.risk_class,
                     "headline": "Refused by safety policy", "headline_en": "Refused by safety policy"}
        m.domains = domains
        transition(db, m, "CLASSIFIED")
        transition(db, m, "FAILED", "policy_refused")
        return
    if decision.decision == "CLARIFY":
        m.domains = domains
        m.clarification = {"type": "scam_warning", "message": decision.explanation}
        transition(db, m, "CLASSIFIED")
        return
    case_domain = next((d for d in domains if d in CASE_DOMAINS), None)
    if "travel" in domains:
        m.scenario = "flight_recovery"
    elif "retail" in domains:
        m.scenario = "retail_reservation"
    elif "crm" in domains and ("follow" in m.intent.lower() or "lead" in m.intent.lower() or "call back" in m.intent.lower()):
        m.scenario = "crm_followup"
    elif case_domain:
        m.scenario = "case_preparation"
        m.bindings = {**m.bindings, "case_domain": case_domain}
    else:
        m.scenario = "unsupported"
    emit(db, m, "CLASSIFIED", {"domains": domains, "confidence": conf, "scenario": m.scenario,
                               "language_detected": lang.code, "language_selected": m.language_selected})
    transition(db, m, "CLASSIFIED")
    if m.scenario == "unsupported" or conf < 0.4:
        m.clarification = {"type": "unsupported_or_unclear", "domains": domains,
                           "message": "I could not map this to a domain with an execution adapter. Describe the "
                                      "problem in a little more detail, or pick a supported mission."}
        emit(db, m, "CLARIFICATION", m.clarification)
        return
    m.clarification = None
    transition(db, m, "DISCOVERING")
    discover(db, m)


def _bindings_complete(m: Mission) -> bool:
    need = {"flight_recovery": ["booking_id"], "retail_reservation": ["product_id", "customer_id", "pickup_date"],
            "crm_followup": ["lead_id", "follow_up_date"], "case_preparation": ["case_domain"]}
    return all(m.bindings.get(k) for k in need.get(m.scenario, []))


def discover(db: Session, m: Mission) -> None:
    t = m.tenant_id
    if m.scenario == "flight_recovery":
        flights = list(db.scalars(select(FxBooking).where(
            FxBooking.tenant_id == t, FxBooking.kind == "flight", FxBooking.status == "CANCELLED_BY_AIRLINE")))
        if not m.bindings.get("booking_id"):
            ref = re.search(r"\b([A-Z]{2}\d{3,4})\b", m.intent)
            hit = next((f for f in flights if ref and f.ref == ref.group(1)), None)
            if hit:
                m.bindings = {**m.bindings, "booking_id": hit.id}
                emit(db, m, "ENTITY_BOUND", {"role": "booking_id", "id": hit.id, "via": "explicit_reference"})
            elif not flights:
                m.clarification = {"type": "no_candidates", "message": "No cancelled bookings found."}
                emit(db, m, "CLARIFICATION", m.clarification)
                return
            else:
                low = m.intent.lower()
                ranked = sorted(flights, key=lambda f: 0 if f.passenger_name.split()[0].lower() in low else 1)
                m.clarification = {"type": "entity_ambiguous", "role": "booking_id",
                                   "message": "Which booking do you mean? I identify bookings by reference, "
                                              "not by name.",
                                   "candidates": [{"id": f.id, "label": f"{f.ref} · {f.passenger_name}",
                                                   "hint": f.title} for f in ranked]}
                emit(db, m, "CLARIFICATION", m.clarification)
                return
    elif m.scenario == "retail_reservation":
        if not m.bindings.get("pickup_date"):
            d = parse_pickup_date(m.intent)
            if d:
                m.bindings = {**m.bindings, "pickup_date": d}
        q = parse_qty(m.intent)
        if q and not m.bindings.get("qty"):
            m.bindings = {**m.bindings, "qty": str(q)}
        if not m.bindings.get("product_id"):
            words = [w.rstrip("s") for w in re.findall(r"\w+", m.intent.lower()) if len(w) > 3]
            prods = list(db.scalars(select(FxProduct).where(FxProduct.tenant_id == t)))
            matches = [p for p in prods if any(w in p.name.lower() for w in words)]
            matches = [p for p in matches if "keyboard" in p.name.lower() or "mouse" in p.name.lower()
                       or any(w in p.name.lower() for w in words if w not in {"this", "that", "with", "have"})]
            if len(matches) == 1:
                m.bindings = {**m.bindings, "product_id": matches[0].id}
                emit(db, m, "ENTITY_BOUND", {"role": "product_id", "id": matches[0].id, "via": "unique_match"})
            else:
                matches.sort(key=lambda p: (p.stock == 0, p.name))
                m.clarification = {"type": "entity_ambiguous", "role": "product_id",
                                   "message": "Which product do you want?" if matches else "No matching product.",
                                   "candidates": [{"id": p.id, "label": p.name,
                                                   "hint": f"₹{p.price_paise // 100:,} · "
                                                           f"{'in stock: ' + str(p.stock) if p.stock else 'out of stock'}"}
                                                  for p in matches]}
                emit(db, m, "CLARIFICATION", m.clarification)
                return
        if not m.bindings.get("customer_id"):
            custs = list(db.scalars(select(FxCustomer).where(FxCustomer.tenant_id == t)))
            low = m.intent.lower()
            custs.sort(key=lambda c: 0 if c.name.split()[0].lower() in low else 1)
            m.clarification = {"type": "entity_ambiguous", "role": "customer_id",
                               "message": "Which customer is this? Customers are matched by record, not by name.",
                               "candidates": [{"id": c.id, "label": c.name, "hint": f"phone ending {c.phone_last4}"}
                                              for c in custs]}
            emit(db, m, "CLARIFICATION", m.clarification)
            return
        if not m.bindings.get("pickup_date"):
            m.clarification = {"type": "missing_field", "role": "pickup_date",
                               "message": "For which date should I reserve it? (YYYY-MM-DD)"}
            emit(db, m, "CLARIFICATION", m.clarification)
            return
    elif m.scenario == "crm_followup":
        if not m.bindings.get("follow_up_date"):
            d = parse_pickup_date(m.intent)
            if d:
                m.bindings = {**m.bindings, "follow_up_date": d}
        if not m.bindings.get("lead_id"):
            leads = list(db.scalars(select(FxLead).where(FxLead.tenant_id == t)))
            low = m.intent.lower()
            leads.sort(key=lambda x: 0 if x.name.split()[0].lower() in low else 1)
            m.clarification = {"type": "entity_ambiguous", "role": "lead_id",
                               "message": "Which contact? Contacts are matched by record, never by name alone.",
                               "candidates": [{"id": x.id, "label": x.name, "hint": f"phone ending {x.phone_last4} · {x.stage}"} for x in leads]}
            emit(db, m, "CLARIFICATION", m.clarification)
            return
        if not m.bindings.get("follow_up_date"):
            m.clarification = {"type": "missing_field", "role": "follow_up_date", "message": "On which date should the follow-up be? (YYYY-MM-DD)"}
            emit(db, m, "CLARIFICATION", m.clarification)
            return
    if not _bindings_complete(m):
        return
    m.clarification = None
    transition(db, m, "ENTITIES_BOUND")
    build_plan(db, m)


def _new_action(db: Session, m: Mission, pos: int, kind: str, connector: str, params: dict, target: str,
                amount: int | None, risk: str) -> Action:
    conn = connector_for(connector, db, m.tenant_id)
    a = Action(tenant_id=m.tenant_id, mission_id=m.id, revision=m.revision, kind=kind, connector=connector,
               params=params, target_entity_id=target, amount_paise=amount, risk=risk, position=pos,
               idempotency_key=op_key(m, kind, target, params), digest="pending")
    db.add(a)
    db.flush()
    a.digest = compute_digest(m, a, conn.version_hash(params))
    return a


def _action_view(a: Action) -> dict:
    return {"id": a.id, "kind": a.kind, "connector": a.connector, "params": a.params, "amount_paise": a.amount_paise,
            "risk": a.risk, "status": a.status, "digest": a.digest, "revision": a.revision, "position": a.position}


def build_plan(db: Session, m: Mission) -> None:
    t = m.tenant_id
    actions: list[Action] = []
    blocked: list[dict] = []
    notes: list[str] = []
    citations: list[dict] = []
    if m.scenario == "flight_recovery":
        b = db.get(FxBooking, m.bindings["booking_id"])
        if not b or b.tenant_id != t:
            transition(db, m, "FAILED", "booking_not_found")
            return
        citations = [{k: v for k, v in d.items()} for d in POLICY_DOCS]
        if b.refund_status == "NOT_REQUESTED":
            actions.append(_new_action(db, m, 0, "refund_request", "booking_fixture", {
                "booking_id": b.id, "booking_ref": b.ref, "passenger_name": b.passenger_name,
                "amount_paise": b.amount_paise, "reason": "involuntary_cancellation"}, b.id, b.amount_paise,
                "financial_request"))
        else:
            notes.append(f"A refund request for {b.ref} already exists (status {b.refund_status}); no second request was planned.")
        hotel = db.scalar(select(FxBooking).where(FxBooking.tenant_id == t, FxBooking.kind == "hotel",
                                                  FxBooking.linked_booking_id == b.id))
        if hotel:
            actions.append(_new_action(db, m, len(actions), "hotel_change_request", "booking_fixture", {
                "booking_id": hotel.id, "booking_ref": hotel.ref, "change": "free_date_change_request",
                "reason": "linked_flight_cancelled"}, hotel.id, None, "booking_change"))
        if re.search(r"calendar|कैलेंडर|காலண்டர்|క్యాలెండర్", m.intent, re.I):
            ev = CalendarConnector(db, t).for_booking(b.id)
            if ev:
                actions.append(_new_action(db, m, len(actions), "calendar_update", "calendar_fixture", {
                    "event_id": ev.id, "title": ev.title, "change": "mark_cancelled_needs_rebook"}, ev.id, None, "calendar_change"))
            else:
                notes.append("No calendar event is linked to this booking, so no calendar change was planned.")
        blocked.append({"kind": "voice_call_airline", "status": "BLOCKED",
                        "reason": "PROVIDER_NOT_CONFIGURED" if not settings.bolna_configured
                        else "NO_AUTHORISED_DESTINATION",
                        "detail": "Calling a real airline needs a configured Bolna agent and an operator-authorised "
                                  "destination. Not simulated."})
        notes += ["Regulatory citations are not included: no verified, dated legal source corpus is ingested yet.",
                  "Effects occur in a local stateful fixture; no real airline or bank is contacted."]
        summary = f"Request refund of ₹{b.amount_paise / 100:,.2f} for {b.ref}" + (
            f" and a date-change for hotel {hotel.ref}" if hotel else "") + (
            " and correct the linked calendar event" if any(a.kind == "calendar_update" for a in actions) else "")
    elif m.scenario == "crm_followup":
        x = db.get(FxLead, m.bindings["lead_id"])
        if not x or x.tenant_id != t:
            transition(db, m, "FAILED", "lead_not_found")
            return
        actions.append(_new_action(db, m, 0, "crm_followup", "crm_fixture", {
            "lead_id": x.id, "lead_name": x.name, "phone_last4": x.phone_last4, "follow_up_date": m.bindings["follow_up_date"],
            "expected_version": x.version, "note": f"Created from request: {m.intent[:120]}"}, x.id, None, "data_write"))
        summary = f"Schedule follow-up for {x.name} (phone ending {x.phone_last4}) on {m.bindings['follow_up_date']}"
        notes.append("Effects occur in a local CRM fixture.")
    elif m.scenario == "case_preparation":
        dom = m.bindings["case_domain"]
        srcs = list(db.scalars(select(RegSource).where(RegSource.tenant_id == t, RegSource.url.contains(dom))))
        ids = [x.id for x in srcs]
        body = f"Complaint category: {dom}\n\nStatement (user's words): {m.intent}\n\n" + (
            "Sources: " + "; ".join(f"[{x.id}] {x.title} ({x.authority}, {x.published})" for x in srcs) if srcs
            else "Sources: none. No verified regulatory source is available, so no entitlement or deadline is asserted.")
        cite.assert_valid(db, t, body, ids)
        citations_view = [{"id": x.id, "title": x.title, "source": x.url, "effective_date": x.published,
                           "jurisdiction": x.authority, "is_fixture": x.is_fixture} for x in srcs]
        citations = citations_view
        actions.append(_new_action(db, m, 0, "prepare_case", "casedesk_fixture", {
            "domain": dom, "title": f"{dom.title()} complaint: {m.intent[:60]}", "body": body, "source_ids": ids}, "case:" + dom, None, "legal_information"))
        summary = f"Prepare a {dom} complaint record in your case desk (not filed with any authority)"
        notes.append("Preparation only: REDEEM has no verified filing channel for this domain.")
    else:
        p, c = db.get(FxProduct, m.bindings["product_id"]), db.get(FxCustomer, m.bindings["customer_id"])
        if not p or p.tenant_id != t or not c or c.tenant_id != t:
            transition(db, m, "FAILED", "target_not_found")
            return
        qty = max(1, min(int(m.bindings.get("qty", 1)), 20))
        if p.stock < qty:
            alts = list(db.scalars(select(FxProduct).where(FxProduct.tenant_id == t, FxProduct.stock > 0,
                                                           FxProduct.name.like("%eyboard%"))))
            m.outcome = {"status": "FAILED", "reason": "out_of_stock", "product": p.name,
                         "alternatives": [{"id": x.id, "name": x.name, "stock": x.stock} for x in alts]}
            emit(db, m, "OUT_OF_STOCK", m.outcome)
            transition(db, m, "FAILED", "out_of_stock")
            return
        actions.append(_new_action(db, m, 0, "reserve_stock", "retail_fixture", {
            "product_id": p.id, "sku": p.sku, "product_name": p.name, "customer_id": c.id,
            "customer_name": c.name, "qty": qty, "pickup_date": m.bindings["pickup_date"],
            "unit_price_paise": p.price_paise}, p.id, p.price_paise * qty, "inventory_write"))
        summary = f"Reserve {qty} × {p.name} for {c.name}, pickup {m.bindings['pickup_date']}"
        notes.append("Effects occur in a local stateful shop fixture.")
    for a in actions:
        emit(db, m, "POLICY", safety.evaluate_action(a.kind, a.params, a.risk).as_dict(), a.id)
    m.plan = {"summary": summary, "actions": [_action_view(a) for a in actions], "blocked": blocked,
              "notes": notes, "policy_citations": citations}
    emit(db, m, "PLAN_READY", {"revision": m.revision, "action_ids": [a.id for a in actions]})
    transition(db, m, "PLAN_READY")
    if not actions:
        m.outcome = {"status": "NO_ACTION_NEEDED", "headline": "Nothing to do", "headline_en": "Nothing to do",
                     "summary": "; ".join(notes) or "No action is required.", "outstanding": []}
        transition(db, m, "CANCELLED", "nothing_to_do")
        return
    transition(db, m, "NEEDS_APPROVAL")


# ---------------------------------------------------------------- revision / binding

def _invalidate_open(db: Session, m: Mission, reason: str) -> None:
    for ap in db.scalars(select(ActionApproval).where(ActionApproval.mission_id == m.id,
                                                      ActionApproval.valid.is_(True))):
        ap.valid, ap.invalidated_reason = False, reason
        emit(db, m, "APPROVAL_INVALIDATED", {"approval_id": ap.id, "reason": reason}, ap.action_id)
    for a in db.scalars(select(Action).where(Action.mission_id == m.id,
                                             Action.status.in_(["AWAITING_APPROVAL", "AUTHORIZED", "PREPARED"]))):
        a.status = "SUPERSEDED"
        emit(db, m, "ACTION_SUPERSEDED", {"revision": a.revision}, a.id)


def revise(db: Session, m: Mission, *, intent: str | None = None, reason: str = "user_revision",
           bindings: dict | None = None, confirmed: bool = False) -> None:
    if m.status in TERMINAL:
        raise EngineError(409, "mission_final", "This mission is finished; start a new mission")
    inflight = db.scalar(select(Action.id).where(Action.mission_id == m.id,
                                                 Action.status.in_(["DISPATCHING", "UNCERTAIN"])))
    if inflight:
        raise EngineError(409, "action_in_flight", "An action is in flight or uncertain; reconcile it first")
    _invalidate_open(db, m, "SUPERSEDED_REVISION")
    m.revision += 1
    if intent is not None and intent != m.intent:
        m.intent = intent
        m.bindings = {}
    if bindings:
        m.bindings = {**m.bindings, **bindings}
    m.plan, m.clarification = {}, None
    db.add(MissionRevision(tenant_id=m.tenant_id, mission_id=m.id, revision=m.revision, intent=m.intent,
                           reason=reason, bindings=m.bindings))
    emit(db, m, "REVISION_CREATED", {"revision": m.revision, "reason": reason, "intent": m.intent})
    old, m.status = m.status, "INTENT_CAPTURED"
    emit(db, m, "STATE", {"from": old, "to": "INTENT_CAPTURED", "reason": reason, "revision": m.revision})
    advance(db, m, confirmed_low_confidence=confirmed)


ALLOWED_ROLES = {"flight_recovery": {"booking_id"}, "retail_reservation": {"product_id", "customer_id", "pickup_date"},
                 "crm_followup": {"lead_id", "follow_up_date"}}


def bind(db: Session, m: Mission, role: str, value: str) -> None:
    if m.status in TERMINAL:
        raise EngineError(409, "mission_final", "This mission is finished")
    if role not in ALLOWED_ROLES.get(m.scenario, set()):
        raise EngineError(422, "invalid_role", f"Cannot bind {role} for scenario {m.scenario}")
    t = m.tenant_id
    if role == "booking_id":
        row = db.get(FxBooking, value)
        ok = bool(row and row.tenant_id == t and row.kind == "flight")
    elif role == "product_id":
        row = db.get(FxProduct, value)
        ok = bool(row and row.tenant_id == t)
    elif role == "customer_id":
        row = db.get(FxCustomer, value)
        ok = bool(row and row.tenant_id == t)
    elif role == "lead_id":
        row = db.get(FxLead, value)
        ok = bool(row and row.tenant_id == t)
    else:
        ok = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
    if not ok:
        raise EngineError(404, "entity_not_found", "No such entity in this workspace")
    if m.plan:  # a plan already exists: changing a bound entity is a revision
        revise(db, m, reason=f"rebind_{role}", bindings={role: value})
        return
    m.bindings = {**m.bindings, role: value}
    emit(db, m, "ENTITY_BOUND", {"role": role, "id": value, "via": "user_selection"})
    if m.status == "DISCOVERING":
        discover(db, m)
    elif m.status in ("CLASSIFIED", "INTENT_CAPTURED"):
        raise EngineError(409, "not_ready", "Mission is not ready for entity binding")


# ---------------------------------------------------------------- approval

def approve(db: Session, m: Mission, user_id: str, approvals: list[dict]) -> None:
    if m.status != "NEEDS_APPROVAL":
        raise EngineError(409, "not_awaiting_approval", f"Mission is {m.status}")
    if not approvals:
        raise EngineError(422, "empty_approval", "Nothing to approve")
    staged = []
    for item in approvals:
        a = db.get(Action, item["action_id"])
        if not a or a.mission_id != m.id or a.tenant_id != m.tenant_id:
            raise EngineError(404, "action_not_found", "Unknown action")
        if a.revision != m.revision or a.status != "AWAITING_APPROVAL":
            raise EngineError(409, "approval_stale", "That action belongs to an older revision or is not pending",
                              code_detail="REVISION_MISMATCH")
        fresh = compute_digest(m, a, connector_for(a.connector, db, m.tenant_id).version_hash(a.params))
        if fresh != a.digest and not _ablated("no_digest"):
            # The target changed after the plan was shown: re-plan under a new revision.
            revise(db, m, reason="target_changed")
            raise EngineError(409, "approval_stale", "The target changed after the plan was shown. A fresh plan "
                              "was prepared; review and approve again.", code_detail="TARGET_CHANGED")
        if not _consteq(item["digest"], a.digest):
            raise EngineError(409, "digest_mismatch", "Approval does not match the exact action shown")
        staged.append(a)
    exp = utcnow() + timedelta(minutes=settings.approval_ttl_minutes)
    for a in staged:
        db.add(ActionApproval(tenant_id=m.tenant_id, mission_id=m.id, action_id=a.id, user_id=user_id,
                              revision=m.revision, digest=a.digest, expires_at=exp))
        a.status = "AUTHORIZED"
        emit(db, m, "APPROVED", {"digest": a.digest, "expires_at": exp.isoformat(), "by": user_id}, a.id)
    transition(db, m, "AUTHORIZED")
    m.plan = {**m.plan, "actions": [_action_view(a) for a in _actions(db, m)]}


def _consteq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


def _actions(db: Session, m: Mission, revision: int | None = None) -> list[Action]:
    rev = m.revision if revision is None else revision
    return list(db.scalars(select(Action).where(Action.mission_id == m.id, Action.revision == rev)
                           .order_by(Action.position)))


# ---------------------------------------------------------------- execution

def execute(db: Session, m: Mission, before_dispatch: Callable[[Action], None] | None = None) -> None:
    if m.status != "AUTHORIZED":
        raise EngineError(409, "not_authorized", f"Mission is {m.status}")
    transition(db, m, "EXECUTING")
    db.commit()
    started_revision = m.revision
    for a in [x for x in _actions(db, m) if x.status == "AUTHORIZED"]:
        if before_dispatch:
            before_dispatch(a)
        db.refresh(m)
        db.refresh(a)
        if m.revision != started_revision or a.status != "AUTHORIZED":
            emit(db, m, "EXECUTION_ABORTED_STALE", {"started_revision": started_revision,
                                                    "current_revision": m.revision}, a.id)
            db.commit()
            return
        ap = db.scalar(select(ActionApproval).where(ActionApproval.action_id == a.id,
                                                    ActionApproval.valid.is_(True))
                       .order_by(ActionApproval.created_at.desc()))
        if not ap or ap.expires_at <= utcnow() or ap.revision != m.revision:
            a.status = "AWAITING_APPROVAL"
            emit(db, m, "APPROVAL_INVALID_AT_DISPATCH", {"reason": "missing_or_expired"}, a.id)
            transition(db, m, "NEEDS_APPROVAL", "approval_invalid")
            db.commit()
            return
        conn = connector_for(a.connector, db, m.tenant_id)
        if not connection_active(db, m.tenant_id, a.connector):
            a.status = "BLOCKED"
            emit(db, m, "CONNECTOR_REVOKED", {"connector": a.connector}, a.id)
            continue
        try:
            fresh = compute_digest(m, a, conn.version_hash(a.params))
        except ProviderRejected:
            fresh = ""
        if fresh != ap.digest and not _ablated("no_digest"):
            ap.valid, ap.invalidated_reason = False, "DIGEST_MISMATCH_AT_DISPATCH"
            a.status = "AWAITING_APPROVAL"
            emit(db, m, "APPROVAL_STALE_AT_DISPATCH", {"reason": "target_or_params_changed"}, a.id)
            transition(db, m, "NEEDS_APPROVAL", "target_changed")
            db.commit()
            return
        snapshot = conn.snapshot(a.params)
        a.status = "DISPATCHING"
        op = ProviderOperation(tenant_id=m.tenant_id, action_id=a.id, provider=a.connector,
                               idempotency_key=a.idempotency_key, status="DISPATCHING")
        db.add(op)
        emit(db, m, "DISPATCHING", {"idempotency_key": a.idempotency_key, "snapshot": snapshot}, a.id)
        db.commit()  # persisted BEFORE the side effect
        try:
            receipt = conn.submit(a.kind, a.params, a.idempotency_key)
        except ProviderTimeout:
            op.status, a.status = "UNCERTAIN", "UNCERTAIN"
            emit(db, m, "ACK_LOST", {"note": "No confirmation received. Will NOT resend; reconciling by lookup."}, a.id)
            db.commit()
            if not _ablated("no_reconcile"):
                reconcile_action(db, m, a, snapshot)
            continue
        except ProviderRejected as e:
            op.status, op.finished_at, a.status = "REJECTED", utcnow(), "FAILED"
            emit(db, m, "REJECTED", {"code": e.code}, a.id)
            db.commit()
            continue
        op.status, op.provider_ref, op.finished_at, op.response = "ACKED", receipt.get("ref"), utcnow(), receipt
        a.status = "AWAITING_PROVIDER"
        emit(db, m, "ACKED", {"provider_ref": receipt.get("ref")}, a.id)
        db.commit()
        verify_action(db, m, a, snapshot)
    finalize(db, m)
    db.commit()


def reconcile_action(db: Session, m: Mission, a: Action, snapshot: dict, attempts: int = 3) -> None:
    """Read-only lookup by idempotency key. Never resubmits."""
    conn = connector_for(a.connector, db, m.tenant_id)
    found = None
    for i in range(attempts):  # bounded; backoff is a no-op for the in-process fixture
        found = conn.lookup(a.idempotency_key)
        emit(db, m, "RECONCILE_LOOKUP", {"attempt": i + 1, "found": bool(found)}, a.id)
        if found:
            break
    op = db.scalar(select(ProviderOperation).where(ProviderOperation.action_id == a.id))
    if found:
        op.status, op.provider_ref, op.finished_at = "RECONCILED", found.ref, utcnow()
        a.status = "AWAITING_PROVIDER"
        emit(db, m, "RECONCILED_FOUND", {"provider_ref": found.ref}, a.id)
        db.commit()
        verify_action(db, m, a, snapshot)
    else:
        emit(db, m, "RECONCILE_NOT_FOUND", {"note": "Provider has no record yet. Human review required."}, a.id)
        db.commit()


def verify_action(db: Session, m: Mission, a: Action, snapshot: dict) -> None:
    conn = connector_for(a.connector, db, m.tenant_id)
    result, evidence = conn.verify(a.kind, a.params, a.idempotency_key, snapshot)
    if _ablated("no_verifier"):  # ablation: trust the provider's acknowledgement instead of the read-back
        result, evidence = "VERIFIED", {"ablated": "no_verifier"}
    db.add(VerificationClaim(tenant_id=m.tenant_id, mission_id=m.id, action_id=a.id,
                             claim=f"{a.kind} applied at provider as approved", result=result, evidence=evidence))
    a.status = "VERIFIED" if result == "VERIFIED" else "FAILED"
    emit(db, m, "VERIFIED" if result == "VERIFIED" else "VERIFICATION_FAILED", evidence, a.id)
    db.commit()


HEADLINES = {
    "en": {"VERIFIED": "Done and verified", "PARTIALLY_VERIFIED": "Partly verified", "UNCERTAIN": "Not yet certain",
           "FAILED": "Could not be completed"},
    "hi": {"VERIFIED": "पूरा हुआ और सत्यापित", "PARTIALLY_VERIFIED": "आंशिक रूप से सत्यापित",
           "UNCERTAIN": "अभी निश्चित नहीं", "FAILED": "पूरा नहीं हो सका"},
    "hinglish": {"VERIFIED": "Ho gaya aur verify bhi", "PARTIALLY_VERIFIED": "Aadha verify hua",
                 "UNCERTAIN": "Abhi pakka nahi", "FAILED": "Complete nahi ho paya"},
    "ta": {"VERIFIED": "முடிந்தது, சரிபார்க்கப்பட்டது", "PARTIALLY_VERIFIED": "பகுதியாக சரிபார்க்கப்பட்டது",
           "UNCERTAIN": "இன்னும் உறுதியில்லை", "FAILED": "முடிக்க இயலவில்லை"},
    "te": {"VERIFIED": "పూర్తయింది, ధృవీకరించబడింది", "PARTIALLY_VERIFIED": "పాక్షికంగా ధృవీకరించబడింది",
           "UNCERTAIN": "ఇంకా ఖచ్చితంగా లేదు", "FAILED": "పూర్తి చేయలేకపోయాం"},
}


def finalize(db: Session, m: Mission) -> None:
    acts = _actions(db, m)
    executed = [a for a in acts if a.status in ("VERIFIED", "FAILED", "UNCERTAIN", "BLOCKED")]
    if m.status == "EXECUTING":
        transition(db, m, "OBSERVING")
    if any(a.status == "UNCERTAIN" for a in acts):
        status = "UNCERTAIN"
    elif executed and all(a.status == "VERIFIED" for a in executed):
        status = "VERIFIED"
    elif any(a.status == "VERIFIED" for a in executed):
        status = "PARTIALLY_VERIFIED"
    else:
        status = "FAILED"
    transition(db, m, status)
    m.plan = {**m.plan, "actions": [_action_view(a) for a in acts]}
    outstanding = [{"action_id": a.id, "kind": a.kind, "reason": "not approved" if a.status == "AWAITING_APPROVAL"
                    else a.status} for a in acts if a.status not in ("VERIFIED",)]
    outstanding += [{"kind": b["kind"], "reason": b["reason"]} for b in m.plan.get("blocked", [])]
    events = list(db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id).order_by(ActionEvent.seq)))
    head = "0" * 64
    for e in events:  # hash chain over the ledger so the receipt is tamper-evident
        head = sha256_hex(head + canonical([e.seq, e.type, e.action_id, e.data]))
    claims = list(db.scalars(select(VerificationClaim).where(VerificationClaim.mission_id == m.id)))
    lang = m.language_selected if m.language_selected in HEADLINES else "en"
    m.outcome = {
        "status": status, "headline": HEADLINES[lang][status], "headline_en": HEADLINES["en"][status],
        "summary": m.plan.get("summary"), "revision": m.revision,
        "verified": [{"action_id": a.id, "kind": a.kind} for a in acts if a.status == "VERIFIED"],
        "failed": [{"action_id": a.id, "kind": a.kind} for a in acts if a.status == "FAILED"],
        "uncertain": [{"action_id": a.id, "kind": a.kind} for a in acts if a.status == "UNCERTAIN"],
        "claims": [{"action_id": c.action_id, "result": c.result, "evidence": c.evidence} for c in claims],
        "outstanding": outstanding, "ledger_events": len(events), "ledger_chain_head": head,
        "generated_at": utcnow().isoformat(),
        "scope": {"stateful_fixture_effects": True, "external_provider_effects": False,
                  "note": "Effects were applied to and verified against a local stateful fixture."},
    }
    emit(db, m, "RECEIPT", {"status": status, "chain_head": head})


def reconcile_mission(db: Session, m: Mission) -> None:
    if m.status != "UNCERTAIN":
        raise EngineError(409, "not_uncertain", f"Mission is {m.status}")
    for a in [x for x in _actions(db, m) if x.status == "UNCERTAIN"]:
        ev = db.scalar(select(ActionEvent).where(ActionEvent.action_id == a.id, ActionEvent.type == "DISPATCHING")
                       .order_by(ActionEvent.seq.desc()))
        reconcile_action(db, m, a, (ev.data.get("snapshot") if ev else {}) or {}, attempts=1)
    transition(db, m, "OBSERVING")
    finalize(db, m)
    db.commit()


def recover_incomplete(db: Session) -> list[str]:
    """Startup recovery: anything left DISPATCHING means we crashed between the write-ahead record and
    the acknowledgement. Look it up read-only; never resend."""
    fixed = []
    for a in list(db.scalars(select(Action).where(Action.status == "DISPATCHING"))):
        m = db.get(Mission, a.mission_id)
        ev = db.scalar(select(ActionEvent).where(ActionEvent.action_id == a.id, ActionEvent.type == "DISPATCHING")
                       .order_by(ActionEvent.seq.desc()))
        snap = (ev.data.get("snapshot") if ev else {}) or {}
        a.status = "UNCERTAIN"
        op = db.scalar(select(ProviderOperation).where(ProviderOperation.action_id == a.id))
        if op:
            op.status = "UNCERTAIN"
        emit(db, m, "RECOVERY_FOUND_DISPATCHING", {"note": "Process stopped mid-dispatch; reconciling by lookup."}, a.id)
        db.commit()
        reconcile_action(db, m, a, snap)
        db.refresh(m)
        if m.status == "EXECUTING":  # remaining authorised actions are not auto-resumed
            finalize(db, m)
        db.commit()
        fixed.append(a.id)
    return fixed


def cancel(db: Session, m: Mission) -> None:
    if m.status in TERMINAL:
        raise EngineError(409, "mission_final", "Already finished")
    if db.scalar(select(Action.id).where(Action.mission_id == m.id, Action.status.in_(["DISPATCHING"]))):
        raise EngineError(409, "action_in_flight", "An action is being dispatched and cannot be cancelled")
    _invalidate_open(db, m, "MISSION_CANCELLED")
    if m.status not in TRANSITIONS or "CANCELLED" not in TRANSITIONS[m.status]:
        raise EngineError(409, "illegal_transition", f"Cannot cancel from {m.status}")
    transition(db, m, "CANCELLED", "user_cancelled")


def mission_view(db: Session, m: Mission) -> dict:
    acts = _actions(db, m)
    return {
        "id": m.id, "status": m.status, "intent": m.intent, "revision": m.revision, "scenario": m.scenario,
        "language_selected": m.language_selected, "language_detected": m.language_detected, "source": m.source,
        "domains": m.domains, "bindings": m.bindings, "clarification": m.clarification,
        "plan": {**(m.plan or {}), "actions": [_action_view(a) for a in acts]} if m.plan else {},
        "outcome": m.outcome, "created_at": m.created_at.isoformat(), "updated_at": m.updated_at.isoformat(),
    }
