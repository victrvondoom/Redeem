"""Per-tenant fixture data. Fictional airline, hotel and shop; no real people or numbers."""
from sqlalchemy.orm import Session

from ..models import Connection, FxBooking, FxCalendarEvent, FxCustomer, FxLead, FxProduct, RegSource

POLICY_DOCS = [{
    "id": "fixture-air-refund-policy-v1",
    "title": "Fixture Air — involuntary cancellation refund terms (FIXTURE)",
    "source": "fixture://fixture-air/refund-policy/v1",
    "effective_date": "2026-01-01",
    "jurisdiction": "IN (fixture; not a statute)",
    "text": "If the airline cancels a flight, the passenger may request a full refund of the base fare "
            "to the original payment method. Requests must be raised through the airline's refund desk.",
    "is_fixture": True,
}]


def seed_tenant(db: Session, tenant_id: str) -> None:
    flight_a = FxBooking(tenant_id=tenant_id, ref="FA2041", kind="flight", passenger_id="pax_rahul_s",
                         passenger_name="Rahul Sharma", title="Fixture Air FA2041 · Mumbai → Chennai",
                         status="CANCELLED_BY_AIRLINE", amount_paise=845000)
    flight_b = FxBooking(tenant_id=tenant_id, ref="FA2087", kind="flight", passenger_id="pax_rahul_v",
                         passenger_name="Rahul Verma", title="Fixture Air FA2087 · Mumbai → Chennai",
                         status="CANCELLED_BY_AIRLINE", amount_paise=912000)
    flight_c = FxBooking(tenant_id=tenant_id, ref="FA3110", kind="flight", passenger_id="pax_priya",
                         passenger_name="Priya Nair", title="Fixture Air FA3110 · Delhi → Kochi",
                         status="CONFIRMED", amount_paise=630000)
    db.add_all([flight_a, flight_b, flight_c])
    db.flush()
    db.add(FxCalendarEvent(tenant_id=tenant_id, title="Flight FA2041 Mumbai → Chennai", linked_booking_id=flight_a.id))
    db.add_all([FxLead(tenant_id=tenant_id, name="Ravi Kumar", phone_last4="2290"),
                FxLead(tenant_id=tenant_id, name="Ravi Kumar", phone_last4="7714"),
                FxLead(tenant_id=tenant_id, name="Meera Joshi", phone_last4="5503", stage="QUALIFIED")])
    db.add(RegSource(tenant_id=tenant_id, url="fixture://reg/telecom-billing-guide", title="Telecom billing complaint guide (FIXTURE)",
                     authority="Fixture Telecom Authority", published="2026-01-01", is_fixture=True,
                     passage="A subscriber may raise a billing complaint with the operator's grievance desk and escalate if unresolved."))
    db.add(FxBooking(tenant_id=tenant_id, ref="HT7712", kind="hotel", passenger_id="pax_rahul_s",
                     passenger_name="Rahul Sharma", title="Marina Stay Chennai · 2 nights",
                     status="CONFIRMED", amount_paise=560000, linked_booking_id=flight_a.id))
    db.add_all([
        FxProduct(tenant_id=tenant_id, sku="KB-MECH-87", name="Keylite K87 Mechanical Keyboard",
                  price_paise=249900, stock=4),
        FxProduct(tenant_id=tenant_id, sku="KB-SLIM-BT", name="Keylite Slim Wireless Keyboard",
                  price_paise=129900, stock=0),
        FxProduct(tenant_id=tenant_id, sku="KB-MEM-104", name="Typa 104 Membrane Keyboard",
                  price_paise=54900, stock=9),
        FxProduct(tenant_id=tenant_id, sku="MS-WL-20", name="Orbit M20 Wireless Mouse",
                  price_paise=69900, stock=12),
        FxCustomer(tenant_id=tenant_id, name="Amit Patel", phone_last4="4821"),
        FxCustomer(tenant_id=tenant_id, name="Amit Patil", phone_last4="9034"),
        FxCustomer(tenant_id=tenant_id, name="Sneha Iyer", phone_last4="1177"),
    ])
    for provider, scopes in (("booking_fixture", ["booking:read", "booking:request"]),
                             ("calendar_fixture", ["calendar:read", "calendar:write"]),
                             ("crm_fixture", ["crm:read", "crm:write"]),
                             ("casedesk_fixture", ["case:write"]),
                             ("retail_fixture", ["catalogue:read", "stock:reserve", "crm:write"])):
        db.add(Connection(tenant_id=tenant_id, provider=provider, kind="fixture", scopes=scopes))
