"""Workflow library: named, typed entry points that start ordinary missions through the one engine."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    scenario: str
    intent_template: str
    inputs: list[str]
    preconditions: list[str]
    credentials: list[str]
    permissions: list[str]
    verification: str
    recovery: str


WORKFLOWS = [
    Workflow("cancelled_flight", "Cancelled flight resolution", "flight_recovery",
             "My flight {booking_ref} was cancelled. I need my refund, my hotel rescheduled, and my calendar corrected.",
             ["booking_ref"], ["booking exists and is cancelled by airline"], ["booking_fixture", "calendar_fixture"],
             ["booking:request", "calendar:write"], "Read back request rows and calendar event", "Reconcile by idempotency key; never resend"),
    Workflow("product_reservation", "Product reservation", "retail_reservation",
             "Customer wants {qty} keyboard reserved for {date}.", ["qty", "date"], ["stock available"], ["retail_fixture"],
             ["stock:reserve"], "Read back reservation and stock decrement", "Atomic decrement; reconcile by key"),
    Workflow("crm_followup", "Customer CRM follow-up", "crm_followup", "Schedule a follow-up for {name} on {date}.",
             ["name", "date"], ["contact selected by record id"], ["crm_fixture"], ["crm:write"],
             "Query CRM record stage and date", "Stale record → re-read and re-approve"),
    Workflow("report_followup", "Follow-up with the latest report (browser)", "browser_followup",
             "Prepare a follow-up for {name} using the latest report, update the CRM and send it after I approve.", ["name"], ["contact exists in the CRM"], ["browser_fixture"],
             ["browser:operate"], "Independent read of the CRM and outbox APIs", "Reconcile by op id; temporal guard on contact + report bytes"),
    Workflow("telecom_complaint", "Telecom billing complaint", "case_preparation",
             "My telecom bill is wrong: {details}", ["details"], [], ["casedesk_fixture"], ["case:write"],
             "Read back case record", "Idempotent case creation"),
    Workflow("housing_deposit", "Rental deposit dispute", "case_preparation", "My landlord is withholding my rental deposit: {details}",
             ["details"], [], ["casedesk_fixture"], ["case:write"], "Read back case record", "Idempotent case creation"),
    Workflow("government_grievance", "Government grievance", "case_preparation", "I want to file a government grievance: {details}",
             ["details"], [], ["casedesk_fixture"], ["case:write"], "Read back case record (preparation only)", "Idempotent case creation"),
    Workflow("healthcare_billing", "Healthcare billing complaint", "case_preparation",
             "My hospital billing has an error: {details}", ["details"], [], ["casedesk_fixture"], ["case:write"],
             "Read back case record", "Idempotent case creation"),
    Workflow("insurance_claim", "Insurance claim complaint", "case_preparation", "My insurance claim was rejected: {details}",
             ["details"], [], ["casedesk_fixture"], ["case:write"], "Read back case record", "Idempotent case creation"),
    Workflow("ecommerce_return", "E-commerce return preparation", "case_preparation", "My online order return was refused: {details}",
             ["details"], [], ["casedesk_fixture"], ["case:write"], "Read back case record", "Idempotent case creation"),
]


def list_workflows() -> list[dict]:
    return [asdict(w) for w in WORKFLOWS]


def get_workflow(wid: str) -> Workflow | None:
    return next((w for w in WORKFLOWS if w.id == wid), None)
