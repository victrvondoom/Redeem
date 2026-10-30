"""Relational model. Identity and transactional state are normalised; provider payloads are JSON."""
import secrets
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, UTCDateTime, utcnow


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
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
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
