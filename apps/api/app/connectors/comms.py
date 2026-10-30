import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxContact, FxMessage
from .base import ProviderRejected, canonical, sha256_hex


class CommsConnector:
    """Prepares message drafts to a bound contact. No messaging provider exists: nothing is ever sent."""

    name = "comms_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    def contact(self, cid: str) -> FxContact | None:
        c = self.db.get(FxContact, cid)
        return c if c and c.tenant_id == self.tenant_id else None

    def version_hash(self, params: dict) -> str:
        c = self.contact(params["contact_id"])
        if not c:
            raise ProviderRejected("contact_not_found")
        return sha256_hex(canonical([c.id, c.name, c.phone_last4, params["body"]]))

    def snapshot(self, params: dict) -> dict:
        return {}

    def lookup(self, idempotency_key: str):
        return self.db.scalar(select(FxMessage).where(FxMessage.tenant_id == self.tenant_id, FxMessage.idempotency_key == idempotency_key))

    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        if not self.contact(params["contact_id"]):
            raise ProviderRejected("contact_not_found")
        key = idempotency_key or f"nokey_{secrets.token_hex(6)}"
        prior = self.lookup(key)
        if prior:
            return {"ref": prior.ref, "status": prior.status, "deduplicated": True}
        ref = f"MSG-{secrets.token_hex(3).upper()}"
        self.db.add(FxMessage(tenant_id=self.tenant_id, contact_id=params["contact_id"], body=params["body"], idempotency_key=key, ref=ref))
        self.db.commit()
        return {"ref": ref, "status": "DRAFTED"}

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        rows = list(self.db.scalars(select(FxMessage).where(FxMessage.tenant_id == self.tenant_id, FxMessage.contact_id == params["contact_id"],
                                                            FxMessage.body == params["body"])))
        mine = [r for r in rows if r.idempotency_key == idempotency_key]
        ev = {"drafts_for_contact": len(rows), "scope": "draft stored in workspace; NOT sent: no messaging provider is connected"}
        if len(rows) > 1:
            return "FAILED", {**ev, "reason": "duplicate_drafts"}
        if not mine:
            return "FAILED", {**ev, "reason": "draft_not_found"}
        return "VERIFIED", {**ev, "provider_ref": mine[0].ref, "status": mine[0].status}
