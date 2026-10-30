from datetime import date

from sqlalchemy import select

from app.models import FxCustomer, FxProduct, FxReservation
from conftest import approve_all, pick


def product(db, tenant, sku):
    db.expire_all()
    return db.scalar(select(FxProduct).where(FxProduct.tenant_id == tenant, FxProduct.sku == sku))


def test_retail_voice_reservation_end_to_end(api, db):
    t = api.me["tenant_id"]
    m = api.post("/api/v1/missions", {"intent": "Customer Amit wants a keyboard and wants it reserved for Saturday",
                                      "source": "voice", "transcript_confidence": 0.93}).json()
    assert "retail" in m["domains"] and m["bindings"]["pickup_date"]
    assert date.fromisoformat(m["bindings"]["pickup_date"]).weekday() == 5  # a real Saturday
    assert m["clarification"]["role"] == "product_id" and len(m["clarification"]["candidates"]) == 3
    m = pick(api, m, "K87")
    # two customers named Amit: identity must be chosen by record, never guessed from the name
    assert m["clarification"]["role"] == "customer_id"
    names = [c["label"] for c in m["clarification"]["candidates"]]
    assert "Amit Patel" in names and "Amit Patil" in names
    m = pick(api, m, "Amit Patel")
    assert m["status"] == "NEEDS_APPROVAL"
    act = m["plan"]["actions"][0]
    assert act["kind"] == "reserve_stock" and act["amount_paise"] == 249900
    assert product(db, t, "KB-MECH-87").stock == 4  # unchanged before approval
    approve_all(api, m)
    done = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    assert done["status"] == "VERIFIED"
    assert product(db, t, "KB-MECH-87").stock == 3
    rs = list(db.scalars(select(FxReservation).where(FxReservation.tenant_id == t)))
    assert len(rs) == 1 and rs[0].pickup_date == m["bindings"]["pickup_date"]
    claim = done["outcome"]["claims"][0]
    assert claim["result"] == "VERIFIED" and claim["evidence"]["stock_before"] == 4 and claim["evidence"]["stock_now"] == 3
    db.expire_all()
    assert db.scalar(select(FxCustomer).where(FxCustomer.id == m["bindings"]["customer_id"])).stage == "RESERVATION"


def test_out_of_stock_fails_honestly_with_alternatives(api):
    m = api.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    m = pick(api, m, "Slim Wireless")
    m = pick(api, m, "Sneha")
    assert m["status"] == "FAILED" and m["outcome"]["reason"] == "out_of_stock"
    assert m["outcome"]["alternatives"]


def test_ack_loss_on_reservation_does_not_double_decrement(api, db):
    t = api.me["tenant_id"]
    m = api.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    m = pick(api, m, "K87")
    m = pick(api, m, "Sneha")
    api.post(f"/api/v1/missions/{m['id']}/faults", {"kind": "ack_loss"})
    approve_all(api, m)
    done = api.post(f"/api/v1/missions/{m['id']}/execute").json()
    assert done["status"] == "VERIFIED"
    assert product(db, t, "KB-MECH-87").stock == 3
    assert len(list(db.scalars(select(FxReservation).where(FxReservation.tenant_id == t)))) == 1


def test_second_approval_for_changed_stock_is_stale(api, db):
    first = api.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    first = pick(api, first, "K87")
    first = pick(api, first, "Sneha")
    second = api.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    second = pick(api, second, "K87")
    second = pick(api, second, "Amit Patel")
    approve_all(api, first)
    api.post(f"/api/v1/missions/{first['id']}/execute")
    r = approve_all(api, second)  # plan was built before stock changed
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_stale"
    assert api.get(f"/api/v1/missions/{second['id']}").json()["revision"] == 2


def test_bind_rejects_cross_tenant_or_invalid_values(api, api2):
    m = api.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    other = api2.post("/api/v1/missions", {"intent": "reserve a keyboard for Saturday"}).json()
    foreign = other["clarification"]["candidates"][0]["id"]
    assert api.post(f"/api/v1/missions/{m['id']}/bind", {"role": "product_id", "value": foreign}).status_code == 404
    assert api.post(f"/api/v1/missions/{m['id']}/bind", {"role": "pickup_date", "value": "tomorrow"}).status_code == 404
    assert api.post(f"/api/v1/missions/{m['id']}/bind", {"role": "evil", "value": "x"}).status_code == 422
