from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxCalendarEvent
from .base import ProviderRejected, canonical, sha256_hex


class CalendarConnector:
    name = "calendar_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    def event(self, event_id: str) -> FxCalendarEvent | None:
        e = self.db.get(FxCalendarEvent, event_id)
        return e if e and e.tenant_id == self.tenant_id else None

    def for_booking(self, booking_id: str) -> FxCalendarEvent | None:
        return self.db.scalar(select(FxCalendarEvent).where(FxCalendarEvent.tenant_id == self.tenant_id,
                                                            FxCalendarEvent.linked_booking_id == booking_id))

    def version_hash(self, params: dict) -> str:
        e = self.event(params["event_id"])
        if not e:
            raise ProviderRejected("event_not_found")
        return sha256_hex(canonical([e.id, e.status, e.version]))

    def snapshot(self, params: dict) -> dict:
        e = self.event(params["event_id"])
        return {"status_before": e.status if e else None}

    def lookup(self, idempotency_key: str):
        return None  # state-based and naturally idempotent: see verify()

    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        e = self.event(params["event_id"])
        if not e:
            raise ProviderRejected("event_not_found")
        if e.status != "CANCELLED_NEEDS_REBOOK":
            e.status, e.version = "CANCELLED_NEEDS_REBOOK", e.version + 1
        self.db.commit()
        return {"ref": e.id, "status": e.status}

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        e = self.event(params["event_id"])
        ev = {"event_status": e.status if e else None, "status_before": snapshot.get("status_before")}
        if not e or e.status != "CANCELLED_NEEDS_REBOOK":
            return "FAILED", {**ev, "reason": "calendar_event_not_updated"}
        return "VERIFIED", {**ev, "provider_ref": e.id}
