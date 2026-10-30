import pytest

from app.domains.language import detect_language, route_domains
from app.orchestration.engine import TRANSITIONS, parse_pickup_date
from app.policy.payment_safety import scan
from datetime import datetime, timezone


def test_payment_scan_flags_otp_link_urgency():
    r = scan("Urgent! Your account will be blocked. Share the OTP and click http://kyc-update.xyz/pay now")
    codes = {i["code"] for i in r["indicators"]}
    assert {"OTP_REQUEST", "URGENCY", "UNVERIFIED_LINK"} <= codes and r["risk_level"] == "high"
    assert scan("Lunch at 1pm?")["risk_level"] == "none_detected"
    assert "not proof of safety" in scan("hello")["disclaimer"]


def test_safety_endpoint(api):
    r = api.post("/api/v1/safety/scan", {"text": "Install AnyDesk so the RBI officer can help"})
    assert r.status_code == 200 and r.json()["risk_level"] == "high"


def test_language_detection():
    assert detect_language("नमस्ते मेरी मदद करो").code == "hi"
    assert detect_language("I need a refund").code == "en"
    assert detect_language("12345").code == "unknown"


def test_domain_routing_confidence():
    d, c = route_domains("hello there")
    assert d == [] and c == 0.0


def test_pickup_date_is_in_ist_and_future():
    fri = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)  # already Saturday 01:30 IST
    assert parse_pickup_date("reserve for Saturday", fri) == "2026-11-07"  # next Saturday, not today


def test_state_machine_has_no_edge_out_of_terminal_states():
    for t in ("VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "CANCELLED", "SUPERSEDED"):
        assert t not in TRANSITIONS
    assert "EXECUTING" not in TRANSITIONS["NEEDS_APPROVAL"]  # approval is mandatory before execution


def test_validation_errors_use_consistent_schema(api):
    r = api.post("/api/v1/missions", {"intent": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.headers["x-request-id"]
    r = api.post("/api/v1/missions", {"intent": "valid intent text", "extra": 1})
    assert r.status_code == 422  # unknown fields rejected
