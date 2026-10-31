"""Relational model. Identity and transactional state are normalised; provider payloads are JSON."""
import secrets
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, UTCDateTime, utcnow
from .security.vault import EncryptedText


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _id(prefix: str):
    return mapped_column(String(40), primary_key=True, default=lambda: new_id(prefix))


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _id("usr")
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = _id("ten")
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = _id("wsp")
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)
    id: Mapped[str] = _id("mem")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    role: Mapped[str] = mapped_column(String(20), default="owner")


class Connection(Base):
    """A connector grant. Fixture connectors are labelled kind='fixture'; none are OAuth."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("tenant_id", "provider"),)
    id: Mapped[str] = _id("con")
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))  # fixture | api_key | oauth
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (Index("ix_mission_tenant_created", "tenant_id", "created_at"),)
    id: Mapped[str] = _id("mis")
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="CREATED")
    intent: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    language_selected: Mapped[str] = mapped_column(String(8), default="en")
    language_detected: Mapped[str] = mapped_column(String(12), default="unknown")
    source: Mapped[str] = mapped_column(String(12), default="text")  # text | voice
    scenario: Mapped[str] = mapped_column(String(40), default="unclassified")
    domains: Mapped[list] = mapped_column(JSON, default=list)
    bindings: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    clarification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class MissionRevision(Base):
    __tablename__ = "mission_revisions"
    __table_args__ = (UniqueConstraint("mission_id", "revision"),)
    id: Mapped[str] = _id("rev")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    intent: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(60))
    bindings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Action(Base):
    __tablename__ = "actions"
    # The key is stable per logical operation across revisions, so uniqueness is per (key, revision).
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", "revision"),)
    id: Mapped[str] = _id("act")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    connector: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON)
    target_entity_id: Mapped[str] = mapped_column(String(40))
    amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    risk: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="AWAITING_APPROVAL")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    digest: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ActionApproval(Base):
    __tablename__ = "action_approvals"
    id: Mapped[str] = _id("apr")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    invalidated_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ActionEvent(Base):
    """Append-only ledger. `seq` gives a total order used by SSE and receipts."""

    __tablename__ = "action_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(String(40), index=True)
    action_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ProviderOperation(Base):
    __tablename__ = "provider_operations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "idempotency_key"),)
    id: Mapped[str] = _id("ops")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    provider_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # DISPATCHING | ACKED | RECONCILED | UNCERTAIN
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    response: Mapped[dict] = mapped_column(JSON, default=dict)


class VerificationClaim(Base):
    __tablename__ = "verification_claims"
    id: Mapped[str] = _id("vfy")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    action_id: Mapped[str] = mapped_column(String(40))
    claim: Mapped[str] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(20))  # VERIFIED | FAILED | UNCERTAIN
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = _id("doc")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    size: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    case_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(30), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    relevance: Mapped[dict] = mapped_column(JSON, default=dict)
    strength: Mapped[dict] = mapped_column(JSON, default=dict)
    duplicate_of: Mapped[str | None] = mapped_column(String(40), nullable=True)
    supersedes: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ocr_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blob_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (UniqueConstraint("provider", "execution_id"),)
    id: Mapped[str] = _id("cal")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), default="bolna")
    kind: Mapped[str] = mapped_column(String(12))  # web | outbound
    execution_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="minted")
    status_rank: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(8), default="en")
    recording_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CallEvent(Base):
    __tablename__ = "call_events"
    __table_args__ = (UniqueConstraint("call_id", "payload_hash"),)
    id: Mapped[str] = _id("cev")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    authoritative: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = _id("cns")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    purpose: Mapped[str] = mapped_column(String(40))  # voice_call | call_recording
    granted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = _id("aud")
    tenant_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# ---- Stateful service fixtures (clearly NOT external providers) ----------------------------


class FxBooking(Base):
    __tablename__ = "fx_bookings"
    __table_args__ = (UniqueConstraint("tenant_id", "ref"),)
    id: Mapped[str] = _id("bkg")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    ref: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))  # flight | hotel
    passenger_id: Mapped[str] = mapped_column(String(40))
    passenger_name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    linked_booking_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    refund_status: Mapped[str] = mapped_column(String(20), default="NOT_REQUESTED")
    version: Mapped[int] = mapped_column(Integer, default=1)


class FxRequest(Base):
    """What the fixture 'airline/hotel desk' has actually received. The verifier reads this table."""

    __tablename__ = "fx_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[str] = _id("fxr")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    booking_id: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(30))
    amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    ref: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FxProduct(Base):
    __tablename__ = "fx_products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku"), CheckConstraint("stock >= 0", name="ck_stock_nonneg"))
    id: Mapped[str] = _id("prd")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    sku: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    price_paise: Mapped[int] = mapped_column(BigInteger)
    stock: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FxCustomer(Base):
    __tablename__ = "fx_customers"
    id: Mapped[str] = _id("cus")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone_last4: Mapped[str] = mapped_column(String(4))
    stage: Mapped[str] = mapped_column(String(20), default="LEAD")


class FxReservation(Base):
    __tablename__ = "fx_reservations"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[str] = _id("rsv")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    customer_id: Mapped[str] = mapped_column(String(40))
    product_id: Mapped[str] = mapped_column(String(40))
    qty: Mapped[int] = mapped_column(Integer)
    pickup_date: Mapped[str] = mapped_column(String(10))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    ref: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FxFault(Base):
    __tablename__ = "fx_faults"
    id: Mapped[str] = _id("flt")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # ack_loss | silent_drop
    remaining: Mapped[int] = mapped_column(Integer, default=1)


class FxCalendarEvent(Base):
    __tablename__ = "fx_calendar_events"
    id: Mapped[str] = _id("cal")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    linked_booking_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")  # ACTIVE | CANCELLED_NEEDS_REBOOK
    version: Mapped[int] = mapped_column(Integer, default=1)


class FxLead(Base):
    """CRM fixture. Contacts are matched by id; names are never identity."""

    __tablename__ = "fx_leads"
    id: Mapped[str] = _id("led")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone_last4: Mapped[str] = mapped_column(String(4))
    stage: Mapped[str] = mapped_column(String(20), default="NEW")
    follow_up_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FxCase(Base):
    """Workspace case desk: complaint/ticket *records prepared inside REDEEM*. Not an external filing."""

    __tablename__ = "fx_cases"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[str] = _id("cas")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    domain: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT_READY")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    ref: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RegSource(Base):
    """Retrieved regulatory/official source passages. Citations may only point at rows here."""

    __tablename__ = "reg_sources"
    id: Mapped[str] = _id("src")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(300))
    authority: Mapped[str] = mapped_column(String(200))
    published: Mapped[str] = mapped_column(String(20))
    passage: Mapped[str] = mapped_column(Text)
    is_fixture: Mapped[bool] = mapped_column(Boolean, default=True)


class FxContact(Base):
    __tablename__ = "fx_contacts"
    id: Mapped[str] = _id("ctc")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    relation: Mapped[str] = mapped_column(String(40))
    phone_last4: Mapped[str] = mapped_column(String(4))


class FxMessage(Base):
    """Prepared message drafts. REDEEM has no messaging provider: drafts are stored, never sent."""

    __tablename__ = "fx_messages"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)
    id: Mapped[str] = _id("msg")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    contact_id: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFTED")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    ref: Mapped[str] = mapped_column(String(30))


class FxFlightOption(Base):
    __tablename__ = "fx_flight_options"
    id: Mapped[str] = _id("opt")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    route: Mapped[str] = mapped_column(String(80))
    flight_no: Mapped[str] = mapped_column(String(20))
    departs: Mapped[str] = mapped_column(String(40))
    price_paise: Mapped[int] = mapped_column(BigInteger)
    seats: Mapped[int] = mapped_column(Integer)


class Case(Base):
    """Consumer case (inherited RECLAIM lifecycle). Every stage output is persisted so a case resumes after refresh/restart."""

    __tablename__ = "cases"
    __table_args__ = (Index("ix_case_tenant_updated", "tenant_id", "updated_at"),)
    id: Mapped[str] = _id("cse")
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[str] = mapped_column(String(40))
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    domain: Mapped[str] = mapped_column(String(30))
    issue_type: Mapped[str] = mapped_column(String(40), default="other")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stage: Mapped[str] = mapped_column(String(30), default="INTAKE")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    intake: Mapped[dict] = mapped_column(JSON, default=dict)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)
    missing: Mapped[list] = mapped_column(JSON, default=list)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    ranking: Mapped[dict] = mapped_column(JSON, default=dict)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    selected_action: Mapped[str | None] = mapped_column(String(60), nullable=True)
    approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    handoff: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    claimed_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    incident_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    followup_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CaseEvent(Base):
    __tablename__ = "case_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    case_id: Mapped[str] = mapped_column(String(40), index=True)
    type: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CaseDraft(Base):
    __tablename__ = "case_drafts"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    id: Mapped[str] = _id("drf")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    case_id: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")  # DRAFT | APPROVED | SUBMITTED | SUPERSEDED
    origin: Mapped[str] = mapped_column(String(16), default="generated")  # generated | user_edit
    cited: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EvidenceClaim(Base):
    __tablename__ = "evidence_claims"
    id: Mapped[str] = _id("clm")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    case_id: Mapped[str] = mapped_column(String(40), index=True)
    field: Mapped[str] = mapped_column(String(60))
    claim: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # SUPPORTED | UNSUPPORTED | CONTRADICTED
    support: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class BrowserSessionRow(Base):
    """One isolated browser context per mission action (inherited RESOLVE cloud-browser design)."""

    __tablename__ = "browser_sessions"
    id: Mapped[str] = _id("bse")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="RUNNING")  # RUNNING | DONE | FAILED | USER_ACTION_REQUIRED
    origins: Mapped[list] = mapped_column(JSON, default=list)
    blocked_requests: Mapped[list] = mapped_column(JSON, default=list)
    user_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class BrowserSnapshot(Base):
    __tablename__ = "browser_snapshots"
    id: Mapped[str] = _id("snp")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phase: Mapped[str] = mapped_column(String(16))  # observe | before | after
    label: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(200))
    dom_sha: Mapped[str] = mapped_column(String(64))
    aria_sha: Mapped[str] = mapped_column(String(64))
    screenshot_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    screenshot_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fused: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MissionTask(Base):
    """Typed task DAG node with ownership, budget, timeout and output; persisted so a mission resumes after refresh/restart."""

    __tablename__ = "mission_tasks"
    id: Mapped[str] = _id("tsk")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(40))
    owner: Mapped[str] = mapped_column(String(30))
    mode: Mapped[str] = mapped_column(String(8), default="read")  # read | write
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")  # QUEUED RUNNING DONE FAILED SKIPPED BLOCKED CANCELLED
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    action_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_budget: Mapped[int] = mapped_column(Integer, default=1)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=10000)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[str] = _id("bmk")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    trials_per_cell: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="RUNNING")  # RUNNING | DONE | FAILED
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EncryptionKey(Base):
    """Wrapped per-workspace data-encryption key (envelope encryption). The wrapped value is useless without the KEK."""
    __tablename__ = "encryption_keys"
    __table_args__ = (UniqueConstraint("scope", "version"),)
    id: Mapped[str] = _id("key")
    scope: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kek_id: Mapped[str] = mapped_column(String(20))
    wrapped: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | retired
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MemoryItem(Base):
    """User-owned persistent memory. `value_enc` is envelope-encrypted; provenance records where the fact came from."""
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_tenant_field", "tenant_id", "field"),)
    id: Mapped[str] = _id("mem")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    category: Mapped[str] = mapped_column(String(30))
    field: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    value_enc: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(20))  # bolna_call | bolna_fixture | typed | mission
    source_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)  # call id
    segment: Mapped[str | None] = mapped_column(String(40), nullable=True)  # transcript segment index
    quote_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # the user's words, encrypted
    explicit: Mapped[bool] = mapped_column(Boolean, default=True)  # explicit statement vs inference
    confidence: Mapped[float] = mapped_column(default=0.5)
    status: Mapped[str] = mapped_column(String(12), default="proposed")  # proposed | confirmed | rejected
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ConversationTurn(Base):
    """Per-user conversation context: every typed/spoken instruction and REDEEM reply, encrypted, so follow-ups keep their context."""
    __tablename__ = "conversation_turns"
    __table_args__ = (Index("ix_turn_user_time", "tenant_id", "user_id", "created_at"), UniqueConstraint("tenant_id", "channel", "ref_id", "idx"))
    id: Mapped[str] = _id("trn")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(12))  # mission | voice | memory | command
    ref_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)  # position inside ref (e.g. transcript line); 0 for single turns
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text_enc: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Integration(Base):
    """A real provider connection (OAuth tokens are envelope-encrypted; never returned by the API)."""
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider"),)
    id: Mapped[str] = _id("int")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default="connected")  # connected | revoked | error
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    account_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_enc: Mapped[str] = mapped_column(Text)
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ExternalAction(Base):
    """A consequential action on a real provider: draft -> approve (digest-bound) -> execute -> verify by read-back. Params are encrypted."""
    __tablename__ = "external_actions"
    __table_args__ = (Index("ix_extact_tenant_status", "tenant_id", "status"),)
    id: Mapped[str] = _id("xac")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30))  # calendar.create_event | email.send
    params_enc: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")  # DRAFT APPROVED EXECUTING DONE VERIFIED UNVERIFIED UNCERTAIN FAILED
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mission_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class BrowserSkill(Base):
    """A browser workflow recorded by performing it once in a real Chromium session (RESOLVE recorded skills). Replays run the same steps in a fresh isolated session."""

    __tablename__ = "browser_skills"
    id: Mapped[str] = _id("skl")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[list] = mapped_column(JSON, default=list)
    recorded_session_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class BrowserSkillRun(Base):
    __tablename__ = "browser_skill_runs"
    id: Mapped[str] = _id("skr")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    skill_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED")  # QUEUED|RUNNING|PAUSED|DONE|FAILED|STOPPED|USER_ACTION_REQUIRED
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Project(Base):
    """Project Store: a named folder that groups a user's missions, cases and documents."""

    __tablename__ = "projects"
    id: Mapped[str] = _id("prj")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ProjectItem(Base):
    __tablename__ = "project_items"
    __table_args__ = (UniqueConstraint("project_id", "kind", "ref_id"),)
    id: Mapped[str] = _id("pri")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # mission | case | document
    ref_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
