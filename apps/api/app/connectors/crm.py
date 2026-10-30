import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxLead
from .base import ProviderRejected, canonical, sha256_hex


class CrmConnector:
    """Stateful CRM fixture: schedule a follow-up and advance the pipeline stage on a lead (by id)."""

    name = "crm_fixture"
    STAGES = ["NEW", "QUALIFIED", "FOLLOW_UP", "WON", "LOST"]

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    def lead(self, lead_id: str) -> FxLead | None:
        x = self.db.get(FxLead, lead_id)
        return x if x and x.tenant_id == self.tenant_id else None

    def search(self, name: str) -> list[FxLead]:
        return list(self.db.scalars(select(FxLead).where(FxLead.tenant_id == self.tenant_id,
                                                         FxLead.name.ilike(f"%{name}%"))))

    def version_hash(self, params: dict) -> str:
        x = self.lead(params["lead_id"])
        if not x:
            raise ProviderRejected("lead_not_found")
        return sha256_hex(canonical([x.id, x.version, x.stage, x.follow_up_date]))

    def snapshot(self, params: dict) -> dict:
        x = self.lead(params["lead_id"])
        return {"version_before": x.version if x else None}

    def lookup(self, idempotency_key: str):
        return None

    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        x = self.lead(params["lead_id"])
        if not x:
            raise ProviderRejected("lead_not_found")
        if x.version == params.get("expected_version", x.version) and not (
                x.follow_up_date == params["follow_up_date"] and x.stage == "FOLLOW_UP"):
            x.stage, x.follow_up_date, x.note = "FOLLOW_UP", params["follow_up_date"], params.get("note")
            x.version += 1
        elif x.version != params.get("expected_version", x.version):
            raise ProviderRejected("stale_contact", "record changed since it was read")
        self.db.commit()
        return {"ref": f"CRM-{secrets.token_hex(3).upper()}", "status": x.stage}

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        x = self.lead(params["lead_id"])  # independent CRM query
        ev = {"stage": x.stage if x else None, "follow_up_date": x.follow_up_date if x else None, "version_now": x.version if x else None}
        if not x or x.stage != "FOLLOW_UP" or x.follow_up_date != params["follow_up_date"]:
            return "FAILED", {**ev, "reason": "crm_record_not_updated"}
        return "VERIFIED", ev
