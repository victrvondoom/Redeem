"""Safety engine: deterministic, independent of any LLM. Every decision carries class, explanation, evidence, audit ref."""
import re
import secrets
from dataclasses import asdict, dataclass, field


@dataclass
class Decision:
    decision: str  # ALLOW | REQUIRE_APPROVAL | REFUSE | CLARIFY | UNTRUSTED
    risk_class: str
    explanation: str
    permission: str = ""
    requires_approval: bool = False
    evidence: list[str] = field(default_factory=list)
    audit_ref: str = field(default_factory=lambda: "pol_" + secrets.token_hex(6))

    def as_dict(self) -> dict:
        return asdict(self)


_CRED = re.compile(r"\b(otp|one[- ]time (password|code)|pin|cvv|password|passcode)\b", re.I)
_SHARE = re.compile(r"\b(share|send|give|tell|provide|read out|enter|collect|ask)\b", re.I)
_CLINICAL = re.compile(r"\b(diagnos\w*|prescrib\w*|what medicine|which medicine|dosage|dose of|treatment for|am i sick)\b", re.I)
_TRANSFER = re.compile(r"\b(transfer|send|wire|pay)\b.{0,30}\b(money|funds|rs\.?|₹|rupees|lakh|crore)\b|\bcharge (my|the) card\b", re.I)
_INJECT = re.compile(r"(ignore (all|previous|prior) (instructions|rules)|you are now|system prompt|disregard|approve (all|every)|"
                     r"do not tell the user|override (the )?(policy|permission))", re.I)


_THIRD_PARTY = re.compile(r"\b(asked me|asking me|someone|caller|they want|wants me|message says|told me to|is asking)\b", re.I)


def evaluate_intent(text: str) -> Decision:
    if _CRED.search(text) and _SHARE.search(text) and _THIRD_PARTY.search(text):
        return Decision("CLARIFY", "identity", "This looks like a scam attempt. Never share an OTP, PIN, CVV or password with anyone, "
                        "including callers claiming to be your bank. REDEEM will never ask for them. Hang up and contact your bank "
                        "through its official app or number.", "none", False, ["third_party_credential_request"])
    if _CRED.search(text) and _SHARE.search(text):
        m = _CRED.search(text).group(0)
        return Decision("REFUSE", "identity", "REDEEM never collects or relays OTPs, PINs, passwords or security codes. "
                        "If someone asked you for one, treat it as a scam.", "none", False, [f"matched:{m.lower()}"])
    if _CLINICAL.search(text):
        return Decision("REFUSE", "health", "REDEEM handles healthcare administration only. It cannot diagnose, prescribe or "
                        "advise on treatment; please consult a qualified clinician.", "none", False, ["clinical_request"])
    if _TRANSFER.search(text):
        return Decision("REFUSE", "financial", "REDEEM never moves money or charges cards autonomously. It can prepare a dispute "
                        "or reminder for your approval instead.", "none", False, ["autonomous_payment_request"])
    return Decision("ALLOW", "none", "No policy concern at intent level.")


_RISK = {"financial_request": ("financial", "booking:request"), "booking_change": ("booking_change", "booking:request"),
         "inventory_write": ("inventory", "stock:reserve"), "data_write": ("privacy", "crm:write"),
         "calendar_change": ("booking_change", "calendar:write"), "legal_information": ("legal", "case:write")}


def evaluate_action(kind: str, params: dict, risk: str) -> Decision:
    cls, perm = _RISK.get(risk, ("general", ""))
    ev = [f"kind:{kind}"] + ([f"amount_paise:{params['amount_paise']}"] if params.get("amount_paise") else [])
    return Decision("REQUIRE_APPROVAL", cls, f"{kind.replace('_', ' ')} changes state and needs your explicit approval bound to its exact "
                    "target, parameters and amount.", perm, True, ev)


def evaluate_untrusted_content(text: str) -> Decision:
    if _INJECT.search(text):
        return Decision("UNTRUSTED", "prompt_injection", "Content from a document, webpage or call contains instruction-like text. "
                        "It is treated as data and can never grant permissions or approve actions.", "none", False, ["instruction_like_text"])
    return Decision("ALLOW", "none", "No instruction-like text detected.")


def evaluate_recipient_change(approved: dict, current: dict) -> Decision:
    if approved.get("target") != current.get("target"):
        return Decision("REQUIRE_APPROVAL", "identity", "The target changed after approval; the earlier approval is void.", "", True,
                        [f"approved:{approved.get('target')}", f"current:{current.get('target')}"])
    return Decision("ALLOW", "none", "Target unchanged.")


def evaluate_unreceipted_claim(claim_has_receipt: bool) -> Decision:
    if not claim_has_receipt:
        return Decision("UNTRUSTED", "verification", "A success claim without a provider receipt is unverified.", "", False, ["no_receipt"])
    return Decision("ALLOW", "none", "Receipt present.")
