"""Stateful booking fixture connector (fictional 'Fixture Air' / hotel desk).

Provider semantics deliberately mirror a real-world desk: it honours an idempotency key *if sent*,
can lose the acknowledgement after applying a request (ack_loss) and can acknowledge without
applying (silent_drop). Faults are injected explicitly and only ever touch fixture rows.
"""
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FxBooking, FxFault, FxRequest
from .base import ProviderRejected, ProviderTimeout, canonical, sha256_hex


def booking_hash(b: FxBooking) -> str:
    return sha256_hex(canonical([b.id, b.status, b.amount_paise, b.version, b.refund_status]))


class BookingConnector:
    name = "booking_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    # ---- reads
    def read_booking(self, booking_id: str) -> FxBooking | None:
        b = self.db.get(FxBooking, booking_id)
        return b if b and b.tenant_id == self.tenant_id else None

    def version_hash(self, params: dict) -> str:
        b = self.read_booking(params["booking_id"])
        if not b:
            raise ProviderRejected("booking_not_found")
        return booking_hash(b)

    def lookup(self, idempotency_key: str) -> FxRequest | None:
        return self.db.scalar(select(FxRequest).where(FxRequest.tenant_id == self.tenant_id,
                                                      FxRequest.idempotency_key == idempotency_key))

    def snapshot(self, params: dict) -> dict:
        return {}

    # ---- faults
    def _take_fault(self, kind: str) -> bool:
        f = self.db.scalar(select(FxFault).where(FxFault.tenant_id == self.tenant_id, FxFault.kind == kind,
                                                 FxFault.remaining > 0))
        if not f:
            return False
        f.remaining -= 1
        self.db.flush()
        return True

    # ---- write
    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        b = self.read_booking(params["booking_id"])
        if not b:
            raise ProviderRejected("booking_not_found")
        silent = self._take_fault("silent_drop")
        lost_ack = self._take_fault("ack_loss")
        key = idempotency_key or f"nokey_{secrets.token_hex(6)}"
        prior = self.lookup(key)
        if prior:
            self.db.commit()
            return {"ref": prior.ref, "status": prior.status, "deduplicated": True}
        ref = f"FX-{secrets.token_hex(3).upper()}"
        if not silent:
            self.db.add(FxRequest(tenant_id=self.tenant_id, booking_id=b.id, kind=kind,
                                  amount_paise=params.get("amount_paise"), idempotency_key=key, ref=ref))
            if kind == "refund_request":
                b.refund_status = "REQUESTED"
                b.version += 1
        self.db.commit()
        if lost_ack:
            raise ProviderTimeout("acknowledgement lost")
        return {"ref": ref, "status": "RECEIVED"}

    # ---- independent verification: reads provider state only, ignores the submit() response
    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        rows = list(self.db.scalars(select(FxRequest).where(
            FxRequest.tenant_id == self.tenant_id, FxRequest.booking_id == params["booking_id"],
            FxRequest.kind == kind)))
        b = self.read_booking(params["booking_id"])
        mine = [r for r in rows if r.idempotency_key == idempotency_key]
        evidence = {"requests_for_booking": len(rows), "matching_idempotency_key": len(mine),
                    "refs": [r.ref for r in rows], "booking_refund_status": b.refund_status if b else None}
        if len(rows) > 1:
            return "FAILED", {**evidence, "reason": "duplicate_requests_detected"}
        if not mine:
            return "FAILED", {**evidence, "reason": "no_matching_request_at_provider"}
        r = mine[0]
        if kind == "refund_request" and (r.amount_paise != params.get("amount_paise")
                                          or (b and b.refund_status != "REQUESTED")):
            return "FAILED", {**evidence, "reason": "provider_state_mismatch"}
        return "VERIFIED", {**evidence, "provider_ref": r.ref, "status": r.status}

    def count_requests(self, booking_id: str, kind: str) -> int:
        return self.db.scalar(select(func.count()).select_from(FxRequest).where(
            FxRequest.tenant_id == self.tenant_id, FxRequest.booking_id == booking_id,
            FxRequest.kind == kind)) or 0
