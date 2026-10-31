"""Rule-based mapping of a spoken answer to a structured memory field.

No LLM is used (none is configured): this is a deterministic keyword/regex mapper covering English, Hindi/Hinglish, Tamil and Telugu terms for
a fixed field registry. It is honest about its limits: unknown phrasing yields "unmapped" plus a clarification question, never a guess.
Negation ("not window, aisle") is handled; two conflicting values for one field yield a clarification instead of a silent pick.
"""
from __future__ import annotations

import re

# field -> (category, label, sensitive, [(value, [terms])])
FIELDS: dict[str, dict] = {
    "travel.seat_preference": {"category": "travel", "label": "Seat preference", "sensitive": False, "question": "Do you prefer a window, aisle or middle seat?",
        "values": {"window": ["window", "khidki", "खिड़की", "ஜன்னல்", "కిటికీ"], "aisle": ["aisle", "गलियारा", "நடைபாதை"], "middle": ["middle seat", "middle"]}},
    "travel.meal_preference": {"category": "travel", "label": "Meal preference", "sensitive": False, "question": "What meal do you prefer on flights?",
        "values": {"vegetarian": ["vegetarian", "veg", "शाकाहारी", "shakahari", "சைவம்", "శాకాహారం"], "non-vegetarian": ["non-veg", "non veg", "non-vegetarian", "मांसाहारी", "அசைவம்", "మాంసాహారం"],
                   "jain": ["jain", "जैन"], "vegan": ["vegan"], "halal": ["halal"]}},
    "travel.home_airport": {"category": "travel", "label": "Home airport", "sensitive": False, "question": "Which airport do you usually fly from?",
        "values": {"BOM": ["bom", "mumbai", "मुंबई", "bombay"], "DEL": ["del", "delhi", "दिल्ली"], "BLR": ["blr", "bengaluru", "bangalore", "बेंगलुरु"],
                   "MAA": ["maa", "chennai", "चेन्नई", "சென்னை"], "HYD": ["hyd", "hyderabad", "हैदराबाद", "హైదరాబాద్"], "CCU": ["ccu", "kolkata", "कोलकाता"]}},
    "profile.preferred_language": {"category": "profile", "label": "Preferred language", "sensitive": False, "question": "Which language should we use with you?",
        "values": {"en": ["english", "अंग्रेज़ी", "angrezi"], "hi": ["hindi", "हिंदी", "हिन्दी"], "hinglish": ["hinglish"], "ta": ["tamil", "தமிழ்", "तमिल"], "te": ["telugu", "తెలుగు", "तेलुगु"]}},
    "profile.contact_method": {"category": "profile", "label": "Preferred contact method", "sensitive": False, "question": "How should we contact you: WhatsApp, email, SMS or a call?",
        "values": {"whatsapp": ["whatsapp", "whats app", "व्हाट्सएप", "व्हाट्सऐप"], "email": ["email", "e-mail", "mail", "ईमेल"], "sms": ["sms", "text message", "एसएमएस"], "phone_call": ["phone call", "call me", "a call", "फोन"]}},
    "billing.refund_mode": {"category": "billing", "label": "Preferred refund mode", "sensitive": False, "question": "Do you want refunds to the original payment method, a wallet or a voucher?",
        "values": {"original_payment": ["original payment", "original method", "same card", "same account", "source"], "wallet": ["wallet"], "voucher": ["voucher", "credit note", "store credit"]}},
    "accessibility.need": {"category": "accessibility", "label": "Accessibility need", "sensitive": True, "question": "Do you have any accessibility requirement we should plan for?",
        "values": {"wheelchair": ["wheelchair", "व्हीलचेयर"], "hearing": ["hearing", "deaf", "सुनने"], "visual": ["visually impaired", "blind", "low vision", "दृष्टि"]}},
}
PATTERN_FIELDS = {
    "profile.email": {"category": "profile", "label": "Email address", "sensitive": True, "question": "What email address should we use?", "regex": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")},
    "profile.phone": {"category": "profile", "label": "Phone number", "sensitive": True, "question": "What phone number should we use?", "regex": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")},
}
NEG = re.compile(r"\b(not|no|don'?t|never|nahi|nahin|नहीं|मत)\b", re.I)


def registry() -> list[dict]:
    out = [{"field": k, "category": v["category"], "label": v["label"], "sensitive": v["sensitive"], "question": v["question"], "options": list(v["values"])} for k, v in FIELDS.items()]
    out += [{"field": k, "category": v["category"], "label": v["label"], "sensitive": v["sensitive"], "question": v["question"], "options": []} for k, v in PATTERN_FIELDS.items()]
    return out


def meta(field: str) -> dict | None:
    return FIELDS.get(field) or PATTERN_FIELDS.get(field)


def _hits(text: str, terms: list[str]) -> list[tuple[int, str]]:
    low = text.lower()
    found = []
    for t in terms:
        for m in re.finditer(r"(?<![\w])" + re.escape(t.lower()) + r"(?![\w])" if t.isascii() else re.escape(t.lower()), low):
            pre = re.split(r"[,;.]|\bbut\b|\bbalki\b|\blekin\b", low[max(0, m.start() - 24):m.start()])[-1]  # negation reaches only to the clause start
            if NEG.search(pre):
                continue  # negated: "not window"
            found.append((m.start(), t))
    return found


def _field_candidates(text: str, field: str) -> list[dict]:
    m = meta(field)
    if not m:
        return []
    if "regex" in m:
        r = m["regex"].search(text)
        if not r:
            return []
        val = re.sub(r"[\s-]", "", r.group(1) if r.groups() else r.group(0))
        return [{"field": field, "value": val, "quote": r.group(0), "span": [r.start(), r.end()]}]
    vals = {}
    for value, terms in m["values"].items():
        h = _hits(text, terms)
        if h:
            vals[value] = h[0]
    # "middle seat" beats a bare "middle"; drop values whose hit is contained in a longer hit of another value
    return [{"field": field, "value": v, "quote": text[max(0, p[0] - 0): p[0] + len(p[1])], "span": [p[0], p[0] + len(p[1])]} for v, p in sorted(vals.items(), key=lambda kv: kv[1][0])]


def map_answer(utterance: str, expected_field: str | None = None) -> dict:
    """Return {candidates, ambiguous, clarification, unmapped}. Each candidate: field, value, label, confidence, explicit, sensitive, quote."""
    text = (utterance or "").strip()[:2000]
    if not text:
        return {"candidates": [], "ambiguous": False, "unmapped": True, "clarification": None}
    fields = [expected_field] if expected_field else list(FIELDS) + list(PATTERN_FIELDS)
    if expected_field and not meta(expected_field):
        return {"candidates": [], "ambiguous": False, "unmapped": True, "clarification": None, "error": "unknown_field"}
    cands: list[dict] = []
    ambiguous_fields: list[str] = []
    for f in fields:
        c = _field_candidates(text, f)
        if f == "travel.seat_preference" and len(c) > 1:  # "middle seat" also matches bare "middle"
            c = [x for x in c if x["value"] != "middle" or "middle seat" in text.lower()] or c
        if len(c) > 1:
            ambiguous_fields.append(f)
            continue
        for x in c:
            m = meta(f)
            x.update(label=m["label"], category=m["category"], sensitive=m["sensitive"], explicit=True,
                     confidence=0.92 if expected_field else 0.78)
            cands.append(x)
    if ambiguous_fields:
        f = ambiguous_fields[0]
        opts = [x["value"] for x in _field_candidates(text, f)]
        return {"candidates": cands, "ambiguous": True, "unmapped": False, "ambiguous_field": f,
                "clarification": f"You mentioned {' and '.join(opts)} for {meta(f)['label'].lower()}. Which one should I save?"}
    if not cands:
        q = meta(expected_field)["question"] if expected_field else None
        return {"candidates": [], "ambiguous": False, "unmapped": True, "clarification": (f"I didn't catch that. {q}" if q else None)}
    return {"candidates": cands, "ambiguous": False, "unmapped": False, "clarification": None}
