"""Deterministic scam-pattern indicators for payment requests. Heuristic; not a fraud guarantee."""
import re
from dataclasses import asdict, dataclass


@dataclass
class Indicator:
    code: str
    severity: str
    message: str


_RULES = [
    ("OTP_REQUEST", "high", r"\b(otp|one[- ]time (password|code)|pin|cvv|password)\b",
     "Genuine banks never ask you to share an OTP, PIN, CVV or password."),
    ("URGENCY", "medium", r"\b(urgent|immediately|within \d+ ?(min|minutes|hours)|last chance|blocked today|"
     r"account (will be )?(blocked|suspended))\b", "Artificial urgency is a common pressure tactic."),
    ("UNVERIFIED_LINK", "high", r"(https?://\S+|\b\w+\.(xyz|top|click|link|online)\b|bit\.ly/\S+)",
     "Payment or KYC links should be opened only from the official app or site."),
    ("IMPERSONATION", "medium", r"\b(rbi|income tax|customs|police|cbi|bank (official|manager|executive)|"
     r"kyc (update|expired))\b", "Authority impersonation is common in payment scams."),
    ("REMOTE_ACCESS", "high", r"\b(anydesk|teamviewer|quicksupport|screen ?share)\b",
     "Never install remote-access apps at a caller's request."),
    ("COLLECT_REQUEST", "medium", r"\b(collect request|approve (the )?request to receive|send .{0,20} to receive)\b",
     "Approving a UPI collect request sends money out; it never receives money."),
]


def scan(text: str) -> dict:
    found = [Indicator(c, s, m) for c, s, rx, m in _RULES if re.search(rx, text, re.I)]
    level = "high" if any(i.severity == "high" for i in found) else ("medium" if found else "none_detected")
    return {"risk_level": level, "indicators": [asdict(i) for i in found],
            "disclaimer": "Heuristic indicators only. Absence of indicators is not proof of safety. "
                          "REDEEM never asks for OTPs, PINs or passwords and never moves money."}
