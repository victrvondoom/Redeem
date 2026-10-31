"""Spoken/typed control commands for a running mission (RESOLVE's intent revision protocol, deterministic, multilingual keywords).
Commands: stop, pause, resume, change, undo, explain, what_happened. Each maps to a real engine operation and every reply states what actually happened."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Action, ActionEvent, Mission
from . import engine

PATTERNS = [
    ("stop", r"\b(stop|cancel|abort|ruko|rok(o|na)|band karo|nahi chahiye)\b|रुको|रोको|रद्द|நிறுத்து|ఆపు"),
    ("pause", r"\b(pause|hold on|hold|wait|ek minute|thehro|ruk jao)\b|ठहरो|थोड़ा रुकिए|காத்திரு|ఆగు"),
    ("resume", r"\b(resume|continue|go ahead|carry on|jaari|chalu karo|aage badho)\b|जारी|आगे बढ़ो|தொடரு|కొనసాగించు"),
    ("undo", r"\b(undo|revert|take (it )?back|wapas|reverse)\b|वापस|पूर्ववत்|திரும்ப"),
    ("what_happened", r"\b(what happened|what's happening|status|kya hua|kahan tak|progress|update)\b|क्या हुआ|என்ன ஆனது|ఏమైంది"),
    ("explain", r"\b(explain|why|how come|kyun|kyon|samjhao)\b|क्यों|समझाओ|ஏன்|ఎందుకు"),
    ("change", r"\b(change|actually|instead|no,|not that|badal(o|na)|nahi,? (wo|woh|that))\b|बदलो|नहीं,|மாற்று|మార్చు"),
]


def interpret(text: str) -> dict:
    low = text.lower().strip()
    for cmd, rx in PATTERNS:
        if re.search(rx, low):
            return {"command": cmd, "confidence": "keyword"}
    return {"command": "unknown", "confidence": "none"}


def _events_summary(db: Session, m: Mission, n: int = 8) -> list[str]:
    ev = list(db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id, ActionEvent.type.in_(
        ["CLASSIFIED", "ENTITY_BOUND", "PLAN_READY", "APPROVED", "DISPATCHING", "ACKED", "ACK_LOST", "RECONCILED_FOUND", "VERIFIED", "VERIFICATION_FAILED", "APPROVAL_INVALIDATED", "REVISION_CREATED",
         "MISSION_PAUSED", "MISSION_RESUMED", "USER_ACTION_REQUIRED", "SKIPPED_DEPENDENCY", "EXECUTION_ABORTED_STALE", "HUMAN_ESCALATION", "RECEIPT"])).order_by(ActionEvent.seq.desc()).limit(n)))
    say = {"CLASSIFIED": "understood the request", "ENTITY_BOUND": "bound a target", "PLAN_READY": "prepared a plan", "APPROVED": "an action was approved", "DISPATCHING": "started an action (recorded before acting)",
           "ACKED": "the provider acknowledged", "ACK_LOST": "an acknowledgement was lost, so I reconciled instead of resending", "RECONCILED_FOUND": "found the existing effect by lookup",
           "VERIFIED": "independently verified an effect", "VERIFICATION_FAILED": "verification FAILED for an action", "APPROVAL_INVALIDATED": "an earlier approval was voided",
           "REVISION_CREATED": "the instruction was revised", "MISSION_PAUSED": "paused", "MISSION_RESUMED": "resumed", "USER_ACTION_REQUIRED": "stopped for a step only you can do",
           "SKIPPED_DEPENDENCY": "skipped an action because what it depends on was not verified", "EXECUTION_ABORTED_STALE": "stopped a stale execution", "HUMAN_ESCALATION": "flagged for a human",
           "RECEIPT": "issued the receipt"}
    return [say.get(e.type, e.type.lower()) for e in reversed(ev)]


def apply(db: Session, m: Mission, text: str) -> dict:
    c = interpret(text)["command"]
    out = {"command": c, "text": text[:200]}
    if c == "stop":
        if m.status in engine.TERMINAL:
            return {**out, "ok": False, "message": f"This mission is already {m.status.lower().replace('_', ' ')}; there is nothing to stop."}
        engine.cancel(db, m)
        return {**out, "ok": True, "message": "Stopped. The mission is cancelled and any approvals are void. Actions already completed are not reversed."}
    if c == "pause":
        engine.pause(db, m)
        return {**out, "ok": True, "message": "Paused. Nothing further will run until you resume."}
    if c == "resume":
        engine.resume(db, m)
        return {**out, "ok": True, "message": "Resumed. Press Run to continue approved actions." if m.status == "AUTHORIZED" else "Resumed."}
    if c == "change":
        if m.status in engine.TERMINAL:
            return {**out, "ok": False, "message": "That mission is finished. Start a new mission with the change."}
        ref = engine.resolve_reference(m, text)
        if ref:
            engine.bind(db, m, ref[0], ref[1])
            return {**out, "ok": True, "message": "Changed. Earlier approvals are void; please review the new plan."}
        engine.revise(db, m, intent=f"{m.intent}. Correction: {text}", reason="user_correction")
        return {**out, "ok": True, "message": f"Revision {m.revision} created. Earlier approvals are void and unfinished actions were replaced; completed work is kept."}
    if c == "undo":
        if m.status in ("AUTHORIZED", "NEEDS_APPROVAL"):
            for a in db.scalars(select(Action).where(Action.mission_id == m.id, Action.revision == m.revision, Action.status == "AUTHORIZED")):
                a.status = "AWAITING_APPROVAL"
            from ..models import ActionApproval
            for ap in db.scalars(select(ActionApproval).where(ActionApproval.mission_id == m.id, ActionApproval.valid.is_(True))):
                ap.valid, ap.invalidated_reason = False, "UNDONE_BY_USER"
            if m.status == "AUTHORIZED":
                engine.transition(db, m, "NEEDS_APPROVAL", "undo_approval")
            engine.emit(db, m, "APPROVAL_UNDONE", {})
            return {**out, "ok": True, "message": "Undone: your approval is withdrawn. Nothing had run."}
        done = [a.kind for a in db.scalars(select(Action).where(Action.mission_id == m.id, Action.status == "VERIFIED"))]
        return {**out, "ok": False, "supported": False, "message": ("Cannot undo: " + ", ".join(done) + " already took effect, and these connectors have no verified reversal. "
                                                                    "I can prepare a corrective request for your approval instead.") if done else "There is nothing to undo."}
    if c == "explain":
        acts = [a for a in db.scalars(select(Action).where(Action.mission_id == m.id).order_by(Action.created_at.desc()))][:3]
        pol = [e.data for e in db.scalars(select(ActionEvent).where(ActionEvent.mission_id == m.id, ActionEvent.type == "POLICY", ActionEvent.action_id.is_not(None)).order_by(ActionEvent.seq.desc()).limit(1))]
        why = f" Policy: {pol[0]['explanation']}" if pol else ""
        return {**out, "ok": True, "message": f"Intent: “{m.intent[:140]}”. Plan: {(m.plan or {}).get('summary', 'not ready yet')}. Status: {m.status.replace('_', ' ').lower()}, revision {m.revision}." + why
                + (" Pending: " + ", ".join(f"{a.kind} ({a.status.lower()})" for a in acts) + "." if acts else "")}
    if c == "what_happened":
        s = _events_summary(db, m)
        return {**out, "ok": True, "message": ("Here is what happened: " + "; ".join(s) + ".") if s else "Nothing has happened yet.", "recent": s}
    return {**out, "ok": False, "message": "I did not catch a command. You can say: stop, pause, resume, change this, undo, explain, or what happened."}
