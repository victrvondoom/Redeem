"""Domain profiles, multi-domain router, document relevance and entity extraction.

Inherited from RECLAIM (MIT): `data/domain_profiles.json` (escalation paths, research questions, evidence schemas for 8 domains) and
`data/domain_keywords.json` (router vocabulary, extracted statically from agents/role_agents/planner.py). Routing is deterministic keyword scoring
like the original. Contact numbers/portals inside the profiles come from RECLAIM and are NOT independently verified by REDEEM."""
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
# RECLAIM name -> REDEEM domain id
ALIAS = {"airlines": "travel", "health_insurance": "insurance"}
REVERSE = {v: k for k, v in ALIAS.items()}
DOMAINS = ["travel", "banking", "insurance", "telecom", "ecommerce", "housing", "government", "healthcare"]
LABEL = {"travel": "Airline & travel", "banking": "Banking & payment safety", "insurance": "Insurance", "telecom": "Telecom", "ecommerce": "E-commerce & retail",
         "housing": "Housing & property", "government": "Government grievances", "healthcare": "Healthcare administration"}


@lru_cache(maxsize=1)
def _profiles() -> dict:
    raw = json.loads((DATA / "domain_profiles.json").read_text(encoding="utf-8"))
    return {ALIAS.get(k, k): v for k, v in raw.items()}


@lru_cache(maxsize=1)
def _keywords() -> dict:
    raw = json.loads((DATA / "domain_keywords.json").read_text(encoding="utf-8"))
    return {ALIAS.get(k, k): [t.lower() for t in v] for k, v in raw.items()}


def profile(domain: str) -> dict:
    return _profiles()[domain]


def kb_domain(domain: str) -> str:
    return REVERSE.get(domain, domain)  # corpus uses 'airlines'


# REDEEM addition: anchor words that identify a domain even when generic words ("bill", "charged") are shared across several domains.
ANCHORS = {"travel": ["flight", "airline", "pnr", "boarding"], "banking": ["bank", "upi", "debit card", "credit card", "neft", "imps"], "insurance": ["insurance", "insurer", "mediclaim", "policyholder"],
           "telecom": ["sim", "recharge", "postpaid", "prepaid", "broadband", "network", "mobile"], "ecommerce": ["order", "seller", "flipkart", "amazon", "delivery", "marketplace"],
           "housing": ["landlord", "tenant", "rent", "rera", "builder", "possession"], "government": ["rti", "passport", "grievance", "department", "municipal", "aadhaar"],
           "healthcare": ["hospital", "clinic", "doctor", "patient", "medical", "discharge"]}


def classify(text: str) -> list[dict]:
    """Multi-domain classification: multi-word terms weigh by word count; scores normalised to the best domain (as in RECLAIM's router)."""
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    raw: dict[str, tuple[float, list[str]]] = {}
    for dom, terms in _keywords().items():
        hit = [t for t in set(terms) if len(t) > 2 and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low)]
        if hit:
            raw[dom] = (sum(1 + 0.5 * (len(t.split()) - 1) for t in hit), sorted(hit)[:8])
    for dom, anchors in ANCHORS.items():
        hit = [a for a in anchors if re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", low)]
        if hit:
            s0, m0 = raw.get(dom, (0.0, []))
            raw[dom] = (s0 + 1.5 * len(hit), sorted(set(m0) | set(hit))[:8])
    for dom, names in PROVIDERS.items():  # a named institution is a much stronger domain signal than shared words like "bill" or "charged"
        hit = [n for n in names if re.search(rf"(?<![a-z0-9]){re.escape(n.lower())}(?![a-z0-9])", low) and n.lower() not in ("rti", "landlord", "builder")]
        if hit:
            s0, m0 = raw.get(dom, (0.0, []))
            raw[dom] = (s0 + 3.0 * len(hit), sorted(set(m0) | {h.lower() for h in hit})[:8])
    if not raw:
        return []
    top = max(v[0] for v in raw.values())
    res = [{"domain": d, "score": round(s, 2), "confidence": round(min(1.0, s / max(top, 3)) * min(1.0, 0.4 + 0.15 * s), 2), "matched": m} for d, (s, m) in raw.items()]
    res.sort(key=lambda x: -x["score"])
    return [r for r in res if r["score"] >= max(1.0, 0.35 * top)]


_IRRELEVANT = ("internship certificate", "completion certificate", "marksheet", "admit card", "hall ticket", "offer letter", "resume", "curriculum vitae",
               "birth certificate", "school certificate", "degree certificate", "payslip", "salary slip", "marriage certificate")


def relevance(text: str, domain: str, filename: str = "") -> dict:
    """Port of RECLAIM's document relevance check: reject obvious noise; otherwise need >=2 domain keyword hits (1 for very short docs)."""
    combined = re.sub(r"\s+", " ", f"{filename} {text[:3000]}".lower())
    for sig in _IRRELEVANT:
        if sig in combined:
            return {"relevant": False, "hits": 0, "reason": f"Looks like a '{sig}', which is unrelated to a {LABEL.get(domain, domain)} case."}
    hits = [k for k in set(_keywords().get(domain, [])) if len(k) > 2 and k in combined]
    ok = len(hits) >= 2 or (len(hits) == 1 and len(text.strip()) < 500)
    return {"relevant": ok, "hits": len(hits), "matched": sorted(hits)[:8],
            "reason": "Relevant to this domain." if ok else f"Only {len(hits)} domain keyword(s) found (need 2). Upload bills, policies, tickets or correspondence."}


# ---- entity extraction (deterministic regexes; every value keeps the span that produced it) ----------------------------------------
PROVIDERS = {
    "travel": ["IndiGo", "Air India Express", "Air India", "SpiceJet", "Vistara", "Akasa Air", "Alliance Air", "Star Air"],
    "banking": ["State Bank of India", "SBI", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak", "Punjab National Bank", "PNB", "Bank of Baroda", "Paytm Payments Bank", "Yes Bank", "IDFC"],
    "telecom": ["Jio", "Airtel", "Vodafone Idea", "BSNL", "MTNL", "ACT Fibernet"],
    "ecommerce": ["Amazon", "Flipkart", "Myntra", "Meesho", "Ajio", "Blinkit", "Zepto", "BigBasket", "Nykaa", "Swiggy", "Zomato"],
    "insurance": ["Star Health", "HDFC ERGO", "ICICI Lombard", "Niva Bupa", "Care Health", "New India Assurance", "LIC", "Bajaj Allianz", "Tata AIG"],
    "housing": ["RERA", "MahaRERA", "landlord", "builder", "housing society"],
    "government": ["CPGRAMS", "RTI", "municipal corporation", "panchayat", "passport office", "regional transport office"],
    "healthcare": ["Apollo", "Fortis", "AIIMS", "Max Healthcare", "Manipal", "Narayana"],
}
_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def _amount(m: re.Match) -> int:
    return int(round(float(m.group(1).replace(",", "")) * 100))


def extract_entities(text: str, domain: str | None = None) -> dict:
    ents: dict[str, list[dict]] = {"amounts": [], "dates": [], "ids": [], "providers": []}
    for m in re.finditer(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text, re.I):
        ents["amounts"].append({"value_paise": _amount(m), "text": m.group(0), "span": list(m.span())})
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b", text, re.I):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif m.group(4):
                d = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            else:
                d = date(int(m.group(9)), _MONTHS[m.group(8).lower()[:3]], int(m.group(7)))
            ents["dates"].append({"iso": d.isoformat(), "text": m.group(0), "span": list(m.span())})
        except ValueError:
            continue
    pats = [("pnr", r"\bpnr\s*[:#]?\s*([A-Z0-9]{6})\b"), ("flight_no", r"\b([A-Z0-9]{2}[- ]?\d{3,4})\b(?=.{0,40}flight|.{0,40}depart)|\bflight\s*(?:no\.?|number)?\s*[:#]?\s*([A-Z0-9]{2}[- ]?\d{3,4})\b"),
            ("order_id", r"\border\s*(?:no\.?|number|id|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{5,})"), ("policy_no", r"\bpolicy\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9/-]{5,})"),
            ("claim_no", r"\bclaim\s*(?:no\.?|number|id|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9/-]{4,})"), ("utr", r"\b(?:utr|rrn|upi ref(?:erence)?)\s*(?:no\.?|number)?\s*[:#]?\s*(\d{9,16})\b"),
            ("complaint_ref", r"\b(?:complaint|ticket|grievance|reference|ref)\s*(?:no\.?|number|id|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9/-]{4,})"), ("account_last4", r"\b(?:a/c|account|card)\D{0,12}(?:x+|\*+)?(\d{4})\b"),
            ("rera_no", r"\b(P\d{11})\b"), ("mobile_last4", r"\b(?:mobile|number|sim)\D{0,10}(?:x+|\*+)?(\d{4})\b")]
    seen = set()
    for kind, rx in pats:
        for m in re.finditer(rx, text, re.I if kind not in ("rera_no",) else 0):
            val = next((g for g in m.groups() if g), None)
            if val and (kind, val.upper()) not in seen and not re.fullmatch(r"(?i)(?:number|details|status|issue)", val):
                seen.add((kind, val.upper()))
                ents["ids"].append({"kind": kind, "value": val.upper() if kind != "utr" else val, "span": list(m.span())})
    low = text.lower()
    for dom in ([domain] if domain else PROVIDERS):
        for name in PROVIDERS.get(dom, []):
            if re.search(rf"(?<![A-Za-z]){re.escape(name.lower())}(?![A-Za-z])", low) and not any(p["name"].lower() == name.lower() for p in ents["providers"]):
                ents["providers"].append({"name": name, "domain": dom})
    return ents
