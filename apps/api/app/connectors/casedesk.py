import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxCase
from .base import canonical, sha256_hex


class CaseDeskConnector:
    """Creates complaint/ticket records inside the workspace case desk. This prepares a case; it never files externally."""

    name = "casedesk_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    def version_hash(self, params: dict) -> str:
        return sha256_hex(canonical([params["domain"], params["title"], params["body"], params.get("source_ids", [])]))

    def snapshot(self, params: dict) -> dict:
        return {}

    def lookup(self, idempotency_key: str):
        return self.db.scalar(select(FxCase).where(FxCase.tenant_id == self.tenant_id, FxCase.idempotency_key == idempotency_key))

    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        key = idempotency_key or f"nokey_{secrets.token_hex(6)}"
        prior = self.lookup(key)
        if prior:
            return {"ref": prior.ref, "status": prior.status, "deduplicated": True}
        ref = f"CASE-{secrets.token_hex(3).upper()}"
        self.db.add(FxCase(tenant_id=self.tenant_id, domain=params["domain"], title=params["title"], body=params["body"],
                           sources=params.get("source_ids", []), idempotency_key=key, ref=ref))
        self.db.commit()
        return {"ref": ref, "status": "DRAFT_READY"}

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        rows = list(self.db.scalars(select(FxCase).where(FxCase.tenant_id == self.tenant_id, FxCase.title == params["title"])))
        mine = [r for r in rows if r.idempotency_key == idempotency_key]
        ev = {"cases_with_title": len(rows), "scope": "internal case record; not filed with any external authority"}
        if len(rows) > 1:
            return "FAILED", {**ev, "reason": "duplicate_cases"}
        if not mine:
            return "FAILED", {**ev, "reason": "case_not_found"}
        return "VERIFIED", {**ev, "provider_ref": mine[0].ref, "status": mine[0].status, "cited_sources": mine[0].sources}
