import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import canonical
from ..models import Call, CallEvent
from .bolna import STATUS_RANK


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
    cost = data.get("total_cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        call.cost = float(cost)
    dur = data.get("conversation_time") or data.get("conversation_duration")
    if isinstance(dur, (int, float)) and not isinstance(dur, bool):
        call.duration_seconds = float(dur)
    if status in ("failed", "error", "busy", "no-answer", "balance-low"):
        call.error_code = status
    return outcome
