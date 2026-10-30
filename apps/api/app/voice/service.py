import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import canonical
from ..models import Call, CallEvent
from ..domains.language import detect_language, route_domains
from ..policy import safety
from .bolna import STATUS_RANK


def analyse_transcript(text: str) -> dict:
    """Heuristic post-call analysis. Confidence is never invented: provider did not supply per-line confidence."""
    events = []
    for line in text.splitlines():
        if ':' in line:
            who, said = line.split(':', 1)
            if who.strip().lower() in ('user', 'customer', 'caller', 'assistant', 'agent'):
                events.append({'speaker': who.strip().lower(), 'text': said.strip(), 'language': detect_language(said).code, 'confidence': None})
    domains, _ = route_domains(text)
    return {'heuristic': True, 'language': detect_language(text).code, 'domains': domains, 'events': events,
            'untrusted_content': safety.evaluate_untrusted_content(text).as_dict(),
            'credential_request_flag': safety.evaluate_intent(text).decision == 'REFUSE'}


def apply_call_update(db: Session, call: Call, data: dict, authoritative: bool) -> str:
    """Store the event (dedup by payload hash). Advance call state only from authoritative data and only
    forward. Transcripts are stored as untrusted data and never trigger actions."""
    digest = hashlib.sha256(canonical(data).encode()).hexdigest()
    if db.scalar(select(CallEvent.id).where(CallEvent.call_id == call.id, CallEvent.payload_hash == digest)):
        return "duplicate"
    status = str(data.get("status") or "unknown")
    db.add(CallEvent(tenant_id=call.tenant_id, call_id=call.id, status=status, authoritative=authoritative,
                     payload_hash=digest, payload=data))
    if not authoritative:
        return "recorded_non_authoritative"
    rank = STATUS_RANK.get(status, 0)
    outcome = "recorded"
    if rank and rank >= call.status_rank:
        call.status, call.status_rank = status, rank
        outcome = "advanced"
    elif rank:
        outcome = "out_of_order_ignored"
    if isinstance(data.get("transcript"), str):
        call.transcript = data["transcript"][:20000]
        call.analysis = analyse_transcript(call.transcript)
    cost = data.get("total_cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        call.cost = float(cost)
    dur = data.get("conversation_time") or data.get("conversation_duration")
    if isinstance(dur, (int, float)) and not isinstance(dur, bool):
        call.duration_seconds = float(dur)
    if status in ("failed", "error", "busy", "no-answer", "balance-low"):
        call.error_code = status
    return outcome
