"""Multi-objective action ranking, ported from RECLAIM (services/decision_engine.py, MIT).
U(a) = w_b*B - w_c*C - w_d*D - w_r*R - w_p*P, min-max normalised; ineligible options (missing evidence / expired deadline) get a -1.0 penalty.
RECLAIM hardcoded its candidate inputs (e.g. benefit 15000, delay 7/14 days). REDEEM keeps the maths but derives inputs from the case
(claimed amount, evidence coverage) and labels every stage-level number as an ASSUMPTION, not a prediction."""
from dataclasses import asdict, dataclass, field


@dataclass
class Weights:
    benefit: float = 0.35
    cost: float = 0.20
    delay: float = 0.20
    risk: float = 0.15
    privacy: float = 0.10


@dataclass
class Candidate:
    key: str
    name: str
    stage: str  # direct | escalation | regulatory
    benefit_inr: float
    cost_inr: float
    delay_days: float
    risk: float
    privacy: float
    prerequisites: list[str] = field(default_factory=list)
    deadline_days: int | None = None
    assumptions: list[str] = field(default_factory=list)


def rank(candidates: list[Candidate], available: set[str], days_since_incident: int, w: Weights | None = None) -> dict:
    w = w or Weights()
    if not candidates:
        return {"ranked": [], "optimal": None, "path": []}
    mb = max((c.benefit_inr for c in candidates), default=1.0) or 1.0
    mc = max((c.cost_inr for c in candidates), default=1.0) or 1.0
    md = max((c.delay_days for c in candidates), default=30.0) or 30.0
    out = []
    for c in candidates:
        b, co, d = c.benefit_inr / mb, (c.cost_inr / mc if mc > 0 else 0.0), min(1.0, c.delay_days / md)
        u = w.benefit * b - w.cost * co - w.delay * d - w.risk * c.risk - w.privacy * c.privacy
        missing = [p for p in c.prerequisites if p not in available]
        expired = bool(c.deadline_days and days_since_incident > c.deadline_days)
        eligible = not missing and not expired
        if not eligible:
            u -= 1.0
        why = []
        if eligible:
            why.append(f"Eligible on current evidence; est. benefit ₹{c.benefit_inr:,.0f}; ~{c.delay_days:.0f} days (assumption).")
        if missing:
            why.append("Blocked by missing evidence: " + ", ".join(missing) + ".")
        if expired:
            why.append(f"Typical window of {c.deadline_days} days (assumption) has passed.")
        out.append({**asdict(c), "utility": round(u, 4), "normalized": {"benefit": round(b, 3), "cost": round(co, 3), "delay": round(d, 3), "risk": c.risk, "privacy": c.privacy},
                    "eligible": eligible, "missing": missing, "deadline_passed": expired, "rationale": " ".join(why)})
    out.sort(key=lambda x: x["utility"], reverse=True)
    path = [e["key"] for s in ("direct", "escalation", "regulatory") for e in out if e["stage"] == s]
    return {"ranked": out, "optimal": out[0]["key"], "path": path, "weights": asdict(w),
            "model": {"formula": "U(a) = w_b*B - w_c*C - w_d*D - w_r*R - w_p*P", "penalty": "-1.0 if evidence missing or window passed",
                      "caveat": "Stage delays, risk and privacy values are heuristic assumptions ported from RECLAIM, not measured outcomes."}}
