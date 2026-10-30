"""Agent roles with least-privilege capabilities and observable, typed contributions.

Each role may do only what its capability set allows; consequential dispatch belongs to the executor alone, and
every agent message is persisted to the mission ledger (event type AGENT) so contributions are inspectable.
Roles are deterministic code responsibilities, not separate model processes.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Action, Mission

CAPABILITIES: dict[str, frozenset[str]] = {
    "planner": frozenset({"plan"}),
    "specialist": frozenset({"read_context", "prepare_action"}),
    "observer": frozenset({"observe", "escalate"}),
    "executor": frozenset({"dispatch"}),
    "verifier": frozenset({"read_verify"}),
    "recovery": frozenset({"read_lookup", "escalate"}),
    "memory": frozenset({"recall"}),
}
CONSEQUENTIAL = frozenset({"dispatch"})


class AgentPermissionError(Exception):
    pass


def require(role: str, capability: str) -> None:
    if capability not in CAPABILITIES.get(role, frozenset()):
        raise AgentPermissionError(f"agent '{role}' lacks capability '{capability}'")


@dataclass(frozen=True)
class AgentMessage:
    agent: str
    kind: str
    data: dict


def say(db: Session, m: Mission, role: str, kind: str, data: dict | None = None, action_id: str | None = None, specialist: str | None = None) -> None:
    from .engine import emit  # local import: engine imports this module

    emit(db, m, "AGENT", {"agent": role + (f":{specialist}" if specialist else ""), "kind": kind, **(data or {})}, action_id)


def recall(db: Session, m: Mission) -> list[dict]:
    """Memory agent: tenant-scoped history of *verified* work on the same targets (other missions only)."""
    require("memory", "recall")
    targets = [v for k, v in m.bindings.items() if k.endswith("_id")]
    if not targets:
        return []
    rows = db.scalars(select(Action).where(Action.tenant_id == m.tenant_id, Action.mission_id != m.id,
                                           Action.target_entity_id.in_(targets), Action.status == "VERIFIED"))
    out = [{"mission_id": a.mission_id, "kind": a.kind, "target": a.target_entity_id} for a in rows]
    say(db, m, "memory", "recall", {"prior_verified_actions": len(out)})
    return out


def observe(db: Session, m: Mission, a: Action, op_status: str | None) -> bool:
    """Observer: provider acknowledged but the independent read-back disagrees => contradictory evidence => escalate."""
    require("observer", "observe")
    contradiction = a.status == "FAILED" and op_status in ("ACKED", "RECONCILED")
    if contradiction:
        require("observer", "escalate")
        m.escalated = True
        say(db, m, "observer", "contradictory_evidence", {"provider_status": op_status, "verified": False}, a.id)
        from .engine import emit
        emit(db, m, "HUMAN_ESCALATION", {"reason": "provider acknowledged but read-back disagrees"}, a.id)
    return contradiction
