"""Domain plugin registry. Status values are truthful and updated only with evidence (FEATURE_MATRIX.md)."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DomainSpec:
    id: str
    name: str
    description: str
    supported_intents: list[str]
    read_capabilities: list[str]
    write_capabilities: list[str]
    required_providers: list[str]
    risk_classes: list[str]
    approval_policy: str
    execution_adapter: str | None
    verification_adapter: str | None
    supported_languages: list[str]
    status: str  # IDEA | SPECIFIED | IMPLEMENTING | LOCALLY_TESTED | PROVIDER_TESTED | END_TO_END_VERIFIED | ...
    backing: str  # fixture | provider | none
    notes: str = ""
    last_verified: str | None = None
    extra: dict = field(default_factory=dict)


_LANGS = ["en", "hi", "hinglish", "ta", "te"]

DOMAINS: list[DomainSpec] = [
    DomainSpec("travel", "Travel & booking", "Cancelled flights, hotel changes, refund requests.",
               ["refund_recovery", "booking_change"], ["read_booking", "read_policy"],
               ["refund_request", "hotel_change_request"], ["booking_fixture"], ["financial_request"],
               "Every write needs a digest-bound approval.", "booking_fixture", "booking_fixture_readback",
               _LANGS, "LOCALLY_TESTED", "fixture",
               "Runs against a stateful local fixture. No real airline is contacted."),
    DomainSpec("consumer_rights", "Consumer rights & disputes", "Complaint preparation with sourced rules.",
               ["dispute_draft"], ["read_policy"], [], [], ["legal_information"],
               "Drafts only; no formal filing without explicit approval and provider capability.",
               None, None, _LANGS, "SPECIFIED", "none",
               "No verified regulatory corpus is bundled yet, so no statute or deadline is ever cited."),
    DomainSpec("banking", "Banking & payment safety", "Scam-pattern scanning of payment requests.",
               ["scam_scan"], ["scan_text"], [], [], ["financial_safety"],
               "Never moves money. Never asks for OTP/PIN/password.", "payment_safety_rules", None,
               ["en", "hinglish"], "LOCALLY_TESTED", "fixture",
               "Rule-based heuristics only: indicators, not guaranteed fraud detection."),
    DomainSpec("retail", "Retail & commerce", "Catalogue, stock and customer reservations.",
               ["reserve_item"], ["search_catalogue", "read_stock"], ["reserve_stock"], ["retail_fixture"],
               ["inventory_write"], "Shop owner approves each reservation.", "retail_fixture",
               "retail_fixture_readback", _LANGS, "LOCALLY_TESTED", "fixture",
               "Fictional Indian electronics shop fixture."),
    DomainSpec("crm", "Sales & CRM", "Customer records and pipeline stage.",
               [], [], [], [], ["data_write"], "-", None, None, [], "SPECIFIED", "none",
               "Customer lookup is used inside the retail flow; no standalone CRM adapter yet."),
    DomainSpec("billing", "Billing & revenue recovery", "Invoice clarification, consent-aware reminders.",
               [], [], [], [], ["financial"], "-", None, None, [], "IDEA", "none"),
    DomainSpec("healthcare", "Healthcare administration", "Appointments and paperwork (never clinical).",
               [], [], [], [], ["sensitive_data"], "-", None, None, [], "IDEA", "none"),
    DomainSpec("telecom", "Telecom", "Billing complaints and plan comparison.", [], [], [], [], [], "-",
               None, None, [], "IDEA", "none"),
    DomainSpec("housing", "Housing", "Deposit disputes and maintenance records.", [], [], [], [], [], "-",
               None, None, [], "IDEA", "none"),
    DomainSpec("government", "Government services", "Grievance and RTI drafting.", [], [], [], [], [], "-",
               None, None, [], "IDEA", "none"),
    DomainSpec("developer", "Developer automation", "Isolated repository tasks.", [], [], [], [], [], "-",
               None, None, [], "IDEA", "none"),
]


def list_domains() -> list[dict]:
    return [asdict(d) for d in DOMAINS]


def get_domain(domain_id: str) -> DomainSpec | None:
    return next((d for d in DOMAINS if d.id == domain_id), None)
