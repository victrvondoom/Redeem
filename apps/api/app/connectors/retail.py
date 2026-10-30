"""Stateful retail + CRM fixture connector (fictional electronics shop)."""
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import FxCustomer, FxFault, FxProduct, FxReservation
from .base import ProviderRejected, ProviderTimeout, canonical, sha256_hex


class RetailConnector:
    name = "retail_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    def product(self, product_id: str) -> FxProduct | None:
        p = self.db.get(FxProduct, product_id)
        return p if p and p.tenant_id == self.tenant_id else None

    def customer(self, customer_id: str) -> FxCustomer | None:
        c = self.db.get(FxCustomer, customer_id)
        return c if c and c.tenant_id == self.tenant_id else None

    def version_hash(self, params: dict) -> str:
        p, c = self.product(params["product_id"]), self.customer(params["customer_id"])
        if not p or not c:
            raise ProviderRejected("target_not_found")
        return sha256_hex(canonical([p.id, p.version, p.price_paise, p.stock, c.id]))

    def snapshot(self, params: dict) -> dict:
        p = self.product(params["product_id"])
        return {"stock_before": p.stock if p else None}

    def lookup(self, idempotency_key: str) -> FxReservation | None:
        return self.db.scalar(select(FxReservation).where(
            FxReservation.tenant_id == self.tenant_id, FxReservation.idempotency_key == idempotency_key))

    def _take_fault(self, kind: str) -> bool:
        f = self.db.scalar(select(FxFault).where(FxFault.tenant_id == self.tenant_id, FxFault.kind == kind,
                                                 FxFault.remaining > 0))
        if not f:
            return False
        f.remaining -= 1
        self.db.flush()
        return True

    def submit(self, kind: str, params: dict, idempotency_key: str | None) -> dict:
        p, c = self.product(params["product_id"]), self.customer(params["customer_id"])
        if not p or not c:
            raise ProviderRejected("target_not_found")
        lost_ack = self._take_fault("ack_loss")
        key = idempotency_key or f"nokey_{secrets.token_hex(6)}"
        prior = self.lookup(key)
        if prior:
            self.db.commit()
            return {"ref": prior.ref, "status": prior.status, "deduplicated": True}
        qty = params["qty"]
        res = self.db.execute(update(FxProduct).where(FxProduct.id == p.id, FxProduct.stock >= qty)
                              .values(stock=FxProduct.stock - qty, version=FxProduct.version + 1))
        if res.rowcount != 1:  # atomic check-and-decrement: no oversell under concurrency
            self.db.rollback()
            raise ProviderRejected("out_of_stock", "insufficient stock")
        c.stage = "RESERVATION"
        ref = f"RSV-{secrets.token_hex(3).upper()}"
        self.db.add(FxReservation(tenant_id=self.tenant_id, customer_id=c.id, product_id=p.id, qty=qty,
                                  pickup_date=params["pickup_date"], idempotency_key=key, ref=ref))
        self.db.commit()
        if lost_ack:
            raise ProviderTimeout("acknowledgement lost")
        return {"ref": ref, "status": "RESERVED"}

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        self.db.expire_all()
        rows = list(self.db.scalars(select(FxReservation).where(
            FxReservation.tenant_id == self.tenant_id, FxReservation.customer_id == params["customer_id"],
            FxReservation.product_id == params["product_id"])))
        mine = [r for r in rows if r.idempotency_key == idempotency_key]
        p, c = self.product(params["product_id"]), self.customer(params["customer_id"])
        evidence = {"reservations_for_pair": len(rows), "stock_now": p.stock if p else None,
                    "stock_before": snapshot.get("stock_before"), "customer_stage": c.stage if c else None}
        if len(rows) > 1:
            return "FAILED", {**evidence, "reason": "duplicate_reservations_detected"}
        if not mine:
            return "FAILED", {**evidence, "reason": "no_matching_reservation"}
        r = mine[0]
        if r.qty != params["qty"] or r.pickup_date != params["pickup_date"]:
            return "FAILED", {**evidence, "reason": "reservation_mismatch"}
        sb = snapshot.get("stock_before")
        if sb is not None and p and p.stock != sb - params["qty"]:
            return "FAILED", {**evidence, "reason": "stock_not_decremented_as_expected"}
        return "VERIFIED", {**evidence, "provider_ref": r.ref, "pickup_date": r.pickup_date, "status": r.status}
