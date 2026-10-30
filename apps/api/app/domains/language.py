"""Deterministic language detection and domain routing.

This is intentionally a transparent rules layer, not an LLM: it supplies a validated, reproducible
first pass. Low-confidence results trigger a clarifying question instead of execution.
"""
import re
from dataclasses import dataclass

SUPPORTED_LANGUAGES = {"en": "English", "hi": "हिन्दी", "hinglish": "Hinglish", "ta": "தமிழ்", "te": "తెలుగు"}

_SCRIPTS = [("hi", re.compile(r"[ऀ-ॿ]")), ("ta", re.compile(r"[஀-௿]")),
            ("te", re.compile(r"[ఀ-౿]"))]
_HINGLISH = {"mera", "meri", "nahi", "nahin", "hai", "hua", "kar", "karo", "chahiye", "paisa", "wapas",
             "madad", "kripya", "abhi", "kya", "mujhe", "ka", "ki", "ko", "raha", "gaya", "gayi", "ho"}
_TANGLISH = {"enoda", "aayiduchu", "varala", "pannunga", "venum", "illa", "irukku", "enna", "panna", "seiyunga"}


@dataclass
class LangResult:
    code: str
    confidence: float
    note: str = ""


def detect_language(text: str) -> LangResult:
    counts = {c: len(rx.findall(text)) for c, rx in _SCRIPTS}
    best, n = max(counts.items(), key=lambda kv: kv[1])
    letters = max(1, len(re.findall(r"\w", text)))
    if n:
        return LangResult(best, min(1.0, 0.5 + n / letters))
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & _TANGLISH:
        # Romanised Tamil: product supports Tamil, we keep the label honest about script.
        return LangResult("ta", 0.7, "romanised Tamil detected")
    if len(words & _HINGLISH) >= 2:
        return LangResult("hinglish", 0.75)
    if re.search(r"[a-z]", text.lower()):
        return LangResult("en", 0.8)
    return LangResult("unknown", 0.0)


DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "travel": ["flight", "airline", "booking", "ticket", "hotel", "pnr", "cancelled", "canceled", "cancel",
               "उड़ान", "फ्लाइट", "विमान", "टिकट", "होटल", "बुकिंग", "रद्द", "விமான", "ரத்து", "டிக்கெட்",
               "ஹோட்டல்", "విమాన", "రద్దు", "టికెట్", "హోటల్"],
    "consumer_rights": ["refund", "complaint", "dispute", "रिफंड", "वापस", "शिकायत", "ரீபண்ட்", "பணம் திரும்ப",
                        "ఫిర్యాదు", "రిఫండ్", "varala"],
    "banking": ["refund", "bank", "upi", "card", "charge", "payment", "debit", "transaction", "बैंक",
                "भुगतान", "पैसे", "கட்டணம்", "பணம்", "చెల్లింపు", "డబ్బు"],
    "retail": ["keyboard", "stock", "reserve", "shop", "product", "mouse", "in stock", "कीबोर्ड", "स्टॉक",
               "दुकान", "கீபோர்டு", "கடை", "కీబోర్డ్", "స్టాక్"],
    "telecom": ["telecom", "mobile bill", "sim ", "broadband", "network outage", "jio", "airtel", "postpaid", "telecom bill"],
    "housing": ["landlord", "rent ", "rental", "deposit", "tenant", "builder", "maintenance complaint"],
    "government": ["government", "grievance", "rti ", "ration", "municipal", "passport"],
    "healthcare": ["hospital", "clinic", "patient", "doctor appointment", "medical bill", "hospital billing"],
    "insurance": ["insurance", "claim was rejected", "policy claim"],
    "ecommerce": ["online order", "return was refused", "refund for order", "amazon", "flipkart", "delivery"],
    "crm": ["customer", "lead", "follow up", "follow-up", "caller", "ग्राहक", "வாடிக்கையாளர்", "కస్టమర్"],
}


def route_domains(text: str) -> tuple[list[str], float]:
    low = text.lower()
    hits = {d: sum(1 for k in kws if k.lower() in low) for d, kws in DOMAIN_KEYWORDS.items()}
    chosen = [d for d, n in sorted(hits.items(), key=lambda kv: -kv[1]) if n > 0]
    total = sum(hits.values())
    confidence = 0.0 if not chosen else min(1.0, 0.4 + 0.15 * total)
    return chosen, confidence
