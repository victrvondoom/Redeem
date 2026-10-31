"""Per-domain case workflows for RECLAIM's eight domains: issue types, critical intake, evidence checklist, escalation candidates, draft templates.
Escalation paths and evidence schemas come from RECLAIM's domain profiles; checklists/issue-type keywords are REDEEM's own deterministic design."""
import re

from . import profiles
from .decision import Candidate

IS = lambda **k: k  # noqa: E731

WF: dict[str, dict] = {
    "travel": {
        "issues": {"cancellation": ["cancel"], "delay": ["delay", "late by", "rescheduled"], "denied_boarding": ["denied boarding", "overbooked", "offloaded"],
                   "baggage": ["baggage", "luggage", "lost bag"], "refund_pending": ["refund", "not refunded", "money back"]},
        "critical": ["flight_number", "scheduled_date", "disruption_type"], "followup_days": 15,
        "checklist": [IS(id="booking_pnr", label="Booking confirmation / e-ticket with PNR", types=["ticket", "booking"]),
                      IS(id="cancellation_notice", label="Airline's cancellation/delay notice (SMS, email, app)", types=["notice", "correspondence", "screenshot"]),
                      IS(id="payment_receipt", label="Payment receipt or statement line", types=["receipt", "invoice", "statement"]),
                      IS(id="airline_response", label="Airline's reply or rejection", types=["rejection_letter", "correspondence"])],
        "prereq": {"direct": ["booking_pnr", "cancellation_notice"], "escalation": ["booking_pnr", "cancellation_notice", "airline_response"], "regulatory": ["booking_pnr", "airline_response"]},
        "remedy": "a refund of the unused fare and any compensation or facilities that apply to this disruption",
    },
    "banking": {
        "issues": {"unauthorized_transaction": ["unauthori", "fraud", "scam", "didn't make", "not me"], "failed_transaction": ["failed", "not reversed", "debited but"],
                   "duplicate_charge": ["duplicate", "charged twice", "double"], "hidden_charges": ["hidden charge", "penalty", "fee"], "loan_card": ["emi", "loan", "credit card"]},
        "critical": ["transaction_date", "transaction_amount", "dispute_type"], "followup_days": 10,
        "checklist": [IS(id="transaction_record", label="Statement / SMS showing the transaction", types=["statement", "receipt", "screenshot"]),
                      IS(id="bank_response", label="Bank's response or rejection", types=["rejection_letter", "correspondence"]),
                      IS(id="complaint_ack", label="Complaint reference given by the bank", types=["notice", "correspondence"]),
                      IS(id="id_proof", label="Account / card details (masked)", types=["id_proof", "statement"])],
        "prereq": {"direct": ["transaction_record"], "escalation": ["transaction_record", "bank_response"], "regulatory": ["transaction_record", "bank_response", "complaint_ack"]},
        "remedy": "reversal or refund of the disputed amount and written confirmation of the outcome",
    },
    "insurance": {
        "issues": {"claim_rejected": ["reject", "denied", "repudiat"], "claim_delay": ["delay", "pending", "not settled"], "cashless_denied": ["cashless"], "premium_dispute": ["premium"]},
        "critical": ["hospital", "coverage_requested", "reason_for_rejection"], "followup_days": 15,
        "checklist": [IS(id="policy_document", label="Policy schedule / terms", types=["policy"]),
                      IS(id="claim_rejection_letter", label="Insurer's rejection or query letter", types=["rejection_letter", "notice"]),
                      IS(id="medical_bills", label="Hospital bills and discharge summary", types=["medical_bill", "bill", "discharge_summary"]),
                      IS(id="claim_form", label="Submitted claim form / acknowledgement", types=["claim_form", "correspondence"])],
        "prereq": {"direct": ["policy_document", "claim_rejection_letter"], "escalation": ["policy_document", "claim_rejection_letter", "medical_bills"], "regulatory": ["policy_document", "claim_rejection_letter", "medical_bills"]},
        "remedy": "reconsideration of the claim and settlement of the admissible amount",
    },
    "telecom": {
        "issues": {"billing": ["bill", "charged", "overcharg", "wrong charge"], "service_outage": ["outage", "no network", "signal", "call drop", "not working"],
                   "porting": ["port", "mnp", "portability"], "plan_mismatch": ["plan", "validity", "benefits"]},
        "critical": ["issue_type"], "followup_days": 10,
        "checklist": [IS(id="bill", label="Bill or recharge receipt showing the issue", types=["bill", "receipt", "invoice"]),
                      IS(id="plan_details", label="Plan details / tariff communication", types=["policy", "correspondence"]),
                      IS(id="complaint_ref", label="Complaint/docket number from the operator", types=["notice", "correspondence"]),
                      IS(id="service_evidence", label="Screenshots or logs of the problem", types=["screenshot"])],
        "prereq": {"direct": ["bill"], "escalation": ["bill", "complaint_ref"], "regulatory": ["bill", "complaint_ref"]},
        "remedy": "correction of the charges or restoration of service, with written confirmation",
    },
    "ecommerce": {
        "issues": {"return_refused": ["return", "refused", "rejected"], "refund_pending": ["refund", "not received"], "wrong_product": ["wrong", "damaged", "fake", "counterfeit"],
                   "non_delivery": ["not delivered", "undelivered", "delivery"], "warranty": ["warranty", "repair"]},
        "critical": ["order_id"], "followup_days": 10,
        "checklist": [IS(id="order_confirmation", label="Order confirmation / invoice", types=["invoice", "booking", "receipt"]),
                      IS(id="seller_response", label="Seller's or platform's reply", types=["correspondence", "rejection_letter"]),
                      IS(id="delivery_evidence", label="Delivery / return tracking or product photos", types=["screenshot", "notice"]),
                      IS(id="payment_proof", label="Payment proof", types=["statement", "receipt"])],
        "prereq": {"direct": ["order_confirmation"], "escalation": ["order_confirmation", "seller_response"], "regulatory": ["order_confirmation", "seller_response"]},
        "remedy": "a refund, replacement or repair as appropriate, with a written timeline",
    },
    "housing": {
        "issues": {"deposit": ["deposit"], "possession_delay": ["possession", "delay", "builder"], "maintenance": ["maintenance", "repair", "leak"], "eviction": ["evict"], "society": ["society"]},
        "critical": ["issue_type"], "followup_days": 15,
        "checklist": [IS(id="agreement", label="Rental / sale agreement or allotment letter", types=["agreement"]),
                      IS(id="payment_receipts", label="Payment receipts (rent, deposit, instalments)", types=["receipt", "statement"]),
                      IS(id="correspondence", label="Messages/notices exchanged with landlord or builder", types=["correspondence", "notice"]),
                      IS(id="property_proof", label="Photos, inspection report or RERA registration", types=["screenshot", "other"])],
        "prereq": {"direct": ["agreement"], "escalation": ["agreement", "payment_receipts", "correspondence"], "regulatory": ["agreement", "payment_receipts", "correspondence"]},
        "remedy": "return of the deposit, completion of the repair or possession, with interest/compensation where the agreement or law provides",
    },
    "government": {
        "issues": {"delay": ["delay", "pending", "not processed"], "rti": ["rti", "right to information"], "certificate": ["certificate", "licence", "license", "passport", "aadhaar"],
                   "service_denial": ["rejected", "denied", "refused"], "corruption": ["bribe", "corrupt"]},
        "critical": ["issue_type"], "followup_days": 30,
        "checklist": [IS(id="application_copy", label="Copy of the application and fee receipt", types=["application", "receipt"]),
                      IS(id="acknowledgement", label="Acknowledgement / registration number", types=["notice", "correspondence"]),
                      IS(id="id_proof", label="ID proof", types=["id_proof"]),
                      IS(id="previous_response", label="Previous reply or rejection from the department", types=["rejection_letter", "notice"])],
        "prereq": {"direct": ["application_copy", "acknowledgement"], "escalation": ["application_copy", "acknowledgement"], "regulatory": ["application_copy", "acknowledgement", "previous_response"]},
        "remedy": "disposal of the application or grievance within a stated period, with reasons if refused",
    },
    "healthcare": {
        "issues": {"billing": ["bill", "overcharg", "invoice"], "records": ["record", "report", "discharge"], "appointment": ["appointment", "booking"], "insurance_admin": ["insurance", "cashless", "tpa"]},
        "critical": ["issue_type"], "followup_days": 10,
        "checklist": [IS(id="bill", label="Itemised hospital bill", types=["medical_bill", "bill", "invoice"]),
                      IS(id="appointment_record", label="Appointment / admission record", types=["booking", "notice"]),
                      IS(id="insurance_card", label="Insurance card or policy", types=["policy", "id_proof"]),
                      IS(id="medical_record", label="Discharge summary / record request", types=["discharge_summary", "other"])],
        "prereq": {"direct": ["bill"], "escalation": ["bill"], "regulatory": ["bill"]},
        "remedy": "correction of the administrative error or release of the requested record",
    },
}

PORTAL_RX = re.compile(r"((?:https?://)?(?:[a-z0-9-]+\.)+(?:gov\.in|nic\.in|org\.in|in|com)(?:/[^\s,;)]*)?)", re.I)
_HELPLINE = re.compile(r"\b(1800[- ]?\d{2,3}[- ]?\d{3,4}|\d{4,6})\b")


def detect_issue(domain: str, text: str) -> str:
    low = text.lower()
    best, score = "other", 0
    for issue, kws in WF[domain]["issues"].items():
        s = sum(1 for k in kws if k in low)
        if s > score:
            best, score = issue, s
    return best


def handoff_steps(domain: str) -> list[dict]:
    steps = []
    for i, step in enumerate(profiles.profile(domain)["escalation_path"]):
        links = [m if m.startswith("http") else "https://" + m for m in PORTAL_RX.findall(step) if "." in m and not m.lower().endswith(("e.g", "e.g."))]
        steps.append({"order": i + 1, "stage": ("direct", "escalation", "regulatory")[min(i, 2)], "text": step, "links": links[:3],
                      "source": "RECLAIM domain profile (not independently verified by REDEEM)"})
    return steps


def candidates(domain: str, claimed_inr: float, coverage: dict[str, float]) -> list[Candidate]:
    """One candidate per escalation step. Benefit = claimed amount (0 if unknown); risk = 1 - evidence coverage for that step's prerequisites;
    delay/privacy/deadline are stage-level ASSUMPTIONS."""
    wf, out = WF[domain], []
    stage_assume = {"direct": (7.0, 0.05, 30), "escalation": (14.0, 0.20, 60), "regulatory": (45.0, 0.50, 180)}
    for st in handoff_steps(domain):
        d, p, dl = stage_assume[st["stage"]]
        pre = wf["prereq"][st["stage"]]
        cov = sum(coverage.get(x, 0.0) for x in pre) / max(1, len(pre))
        out.append(Candidate(key=f"{st['stage']}_{st['order']}", name=st["text"].split(" -- ")[0][:140], stage=st["stage"], benefit_inr=claimed_inr, cost_inr=0.0, delay_days=d,
                             risk=round(1 - cov, 2), privacy=p, prerequisites=pre, deadline_days=dl,
                             assumptions=[f"delay ~{d:.0f} days, privacy exposure {p}, window {dl} days are heuristic stage defaults (from RECLAIM)"]))
    return out


def draft(domain: str, case: dict, passages: list[dict]) -> str:
    prof, wf = profiles.profile(domain), WF[domain]
    f = {k: v for k, v in (case.get("intake") or {}).items() if v}
    facts = "\n".join(f"- {k.replace('_', ' ').capitalize()}: {v}" for k, v in f.items()) or "- (no structured facts captured yet)"
    ev = "\n".join(f"- {d['filename']} ({d.get('doc_type', 'document')}, sha256 {d['sha256'][:10]}…)" for d in case.get("documents", [])) or "- (no documents attached yet)"
    basis = ""
    for h in passages[:2]:
        if h["evidence_scores"]["confidence"] >= 0.3:
            tag = "official source retrieved by RECLAIM" if h["provenance"] == "scraped_official" else "authored guidance (not an official text)"
            basis += f"\n[{h['id']}] {h['title']} — {h['authority'] or 'unknown authority'} ({tag}): \"{h['passage'][:260].strip()}…\""
    subject = f"{('Complaint' if prof.get('is_dispute', True) is not False else 'Administrative request')}: {case.get('issue_type', 'issue').replace('_', ' ')} — {case.get('provider') or prof['counterparty']}"
    return (f"Subject: {subject}\n\nTo: The Grievance / Nodal Officer, {case.get('provider') or prof['counterparty']}\n\n"
            f"I am writing as a {prof['entity']} regarding the matter below.\n\nSummary:\n{case.get('description', '').strip()[:900]}\n\nFacts and references:\n{facts}\n\n"
            f"Supporting documents attached:\n{ev}\n\n"
            + (f"Reference material (for context; please verify before relying on it):{basis}\n\n" if basis else "")
            + f"What I request: {wf['remedy']}. Please acknowledge this request and share a written response within {wf['followup_days']} days. "
            f"If it cannot be resolved, I intend to use the escalation route: {prof['regulator']}.\n\nThis draft was prepared by REDEEM for the user's review. It does not state any legal entitlement "
            f"as established; requested timelines are requests, not statutory deadlines.\n\nSincerely,\n{case.get('user_name', '[Your name]')}\n")
