"""Deterministic demo scenarios. They drive the SAME engine as real missions; the signed-in user's click on 'Run' is the
approval (recorded as DEMO_AUTO_APPROVAL). Fixtures are reset first so every run is repeatable. Fixture-backed only."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .core.deps import Ctx
from .fixtures.seed import seed_tenant
from .models import (Connection, FxBooking, FxCalendarEvent, FxCase, FxContact, FxCustomer, FxFault, FxFlightOption, FxLead, FxMessage,
                     FxProduct, FxRequest, FxReservation, Mission, RegSource)
from .orchestration import engine

FIXTURES = (FxFault, FxRequest, FxReservation, FxMessage, FxCase, FxCalendarEvent, FxFlightOption, FxContact, FxLead, FxBooking,
            FxProduct, FxCustomer, RegSource, Connection)

A_INTENT = ("My flight FA2041 was cancelled. I need my refund, my hotel rescheduled, my calendar corrected, "
            "and please inform my family. Also find me an alternative.")
B_INTENT = "A customer called the shop: Amit Patel wants two keyboards reserved for tomorrow"
C_INTENT = "Flight cancelled for Rahul, refund please"


def reset_fixtures(db: Session, tenant_id: str) -> None:
    for model in FIXTURES:
        db.execute(delete(model).where(model.tenant_id == tenant_id))
    seed_tenant(db, tenant_id)
    db.commit()


def _new(db: Session, ctx: Ctx, intent: str) -> Mission:
    m = Mission(tenant_id=ctx.tenant_id, workspace_id=ctx.workspace_id, user_id=ctx.user.id, intent=intent, language_selected=ctx.user.language)
    db.add(m)
    db.flush()
    engine.emit(db, m, "DEMO_SCENARIO", {"note": "Demo scenario on local fixtures. Not a live provider."})
    engine.start_mission(db, m)
    db.commit()
    return m


def _approve_all(db: Session, ctx: Ctx, m: Mission) -> None:
    items = [{"action_id": a.id, "digest": a.digest} for a in engine._actions(db, m) if a.status == "AWAITING_APPROVAL"]
    engine.emit(db, m, "DEMO_AUTO_APPROVAL", {"by": ctx.user.id, "note": "Your click on 'Run scenario' is the approval"})
    engine.approve(db, m, ctx.user.id, items)
    db.commit()


def run(db: Session, ctx: Ctx, scenario: str) -> dict:
    t = ctx.tenant_id
    reset_fixtures(db, t)
    if scenario == "a":
        m = _new(db, ctx, A_INTENT)
        _approve_all(db, ctx, m)
        engine.execute(db, m)
        db.commit()
        return {"scenario": "a", "mission_id": m.id, "status": m.status}
    if scenario == "b":
        m = _new(db, ctx, B_INTENT)
        prod = db.scalar(select(FxProduct).where(FxProduct.tenant_id == t, FxProduct.sku == "KB-MECH-87"))
        cust = db.scalar(select(FxCustomer).where(FxCustomer.tenant_id == t, FxCustomer.name == "Amit Patel"))
        engine.bind(db, m, "product_id", prod.id)
        engine.bind(db, m, "customer_id", cust.id)
        db.commit()
        _approve_all(db, ctx, m)
        engine.execute(db, m)
        db.commit()
        return {"scenario": "b", "mission_id": m.id, "status": m.status}
    if scenario == "c":
        m = _new(db, ctx, C_INTENT)
        sharma = db.scalar(select(FxBooking).where(FxBooking.tenant_id == t, FxBooking.ref == "FA2041"))
        verma = db.scalar(select(FxBooking).where(FxBooking.tenant_id == t, FxBooking.ref == "FA2087"))
        engine.bind(db, m, "booking_id", sharma.id)
        db.commit()
        _approve_all(db, ctx, m)
        stale = [(a.id, a.digest) for a in engine._actions(db, m)]
        db.add(FxFault(tenant_id=t, kind="ack_loss", remaining=1))
        engine.emit(db, m, "FAULT_ARMED", {"kind": "ack_loss", "scope": "fixture_provider"})
        engine.bind(db, m, "booking_id", verma.id)  # "Wait, wrong passenger. I mean the other Rahul."
        db.commit()
        replay_blocked = False
        try:
            engine.approve(db, m, ctx.user.id, [{"action_id": stale[0][0], "digest": stale[0][1]}])
        except engine.EngineError:
            db.rollback()
            replay_blocked = True
        db.refresh(m)
        _approve_all(db, ctx, m)
        engine.execute(db, m)
        db.commit()
        n = lambda b: db.query(FxRequest).filter(FxRequest.tenant_id == t, FxRequest.booking_id == b.id, FxRequest.kind == "refund_request").count()  # noqa: E731
        return {"scenario": "c", "mission_id": m.id, "status": m.status, "revision": m.revision, "stale_approval_replay_blocked": replay_blocked,
                "refund_requests_on_intended_booking": n(verma), "refund_requests_on_wrong_booking": n(sharma)}
    raise ValueError(scenario)
