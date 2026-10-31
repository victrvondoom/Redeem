"""Persisted typed task DAG (RESOLVE's supervisor/agent-runtime design on REDEEM's engine).
Every mission revision gets nodes with an owner role, dependencies, budget (retries/timeouts), input and output. Read-only tasks may run concurrently with
bounded retries/timeouts; write tasks are the engine's actions and run serialised by the executor. Statuses are written as work really happens."""
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Action, Mission, MissionTask


def add(db: Session, m: Mission, kind: str, owner: str, mode: str = "read", depends_on: list[str] | None = None, status: str = "QUEUED", input: dict | None = None,
        output: dict | None = None, action_id: str | None = None, timeout_ms: int = 10000, retry_budget: int = 1) -> MissionTask:
    t = MissionTask(tenant_id=m.tenant_id, mission_id=m.id, revision=m.revision, kind=kind, owner=owner, mode=mode, depends_on=depends_on or [], status=status, input=input or {},
                    output=output or {}, action_id=action_id, timeout_ms=timeout_ms, retry_budget=retry_budget)
    if status in ("DONE", "FAILED"):
        t.started_at = t.finished_at = utcnow()
    db.add(t)
    db.flush()
    return t


def run_read_tasks(db: Session, m: Mission, specs: list[dict]) -> dict[str, MissionTask]:
    """specs: {kind, owner, fn, timeout_ms, retries}. fn() runs in a worker thread (own DB session if it needs one). Independent reads run concurrently;
    each has a timeout and a retry budget; failures are recorded, never swallowed."""
    results: dict[str, tuple[str, dict, int, str | None, float]] = {}

    def work(spec):
        t0, last = time.perf_counter(), None
        for attempt in range(1, spec.get("retries", 1) + 2):
            try:
                return spec["kind"], "DONE", spec["fn"](), attempt, None, (time.perf_counter() - t0) * 1000
            except Exception as e:  # noqa: BLE001 - recorded on the task
                last = f"{type(e).__name__}: {str(e)[:160]}"
        return spec["kind"], "FAILED", {}, spec.get("retries", 1) + 1, last, (time.perf_counter() - t0) * 1000

    with ThreadPoolExecutor(max(1, min(6, len(specs)))) as ex:
        futs = {ex.submit(work, s): s for s in specs}
        for f, s in futs.items():
            try:
                k, st, out, att, err, ms = f.result(timeout=s.get("timeout_ms", 10000) / 1000 + 1)
            except FutTimeout:
                k, st, out, att, err, ms = s["kind"], "FAILED", {}, 1, "timeout", s.get("timeout_ms", 10000)
            results[k] = (st, out, att, err, ms)
    tasks = {}
    for s in specs:
        st, out, att, err, ms = results[s["kind"]]
        t = add(db, m, s["kind"], s["owner"], "read", s.get("depends_on", []), st, s.get("input", {}), {**(out if isinstance(out, dict) else {"value": out}), "elapsed_ms": round(ms, 1), "concurrent": len(specs) > 1}, None,
                s.get("timeout_ms", 10000), s.get("retries", 1))
        t.attempts, t.error = att, err
        tasks[s["kind"]] = t
    return tasks


def for_action(db: Session, m: Mission, action_id: str) -> list[MissionTask]:
    return list(db.scalars(select(MissionTask).where(MissionTask.mission_id == m.id, MissionTask.action_id == action_id, MissionTask.revision == m.revision)))


def mark(db: Session, m: Mission, action_id: str, kind_mode: str, status: str, output: dict | None = None, error: str | None = None) -> None:
    """kind_mode: 'write' (the executor's task) or 'verify'."""
    for t in for_action(db, m, action_id):
        if (kind_mode == "write") == (t.mode == "write"):
            t.status = status
            if status == "RUNNING":
                t.started_at, t.attempts = utcnow(), t.attempts + 1
            else:
                t.finished_at = utcnow()
            if output is not None:
                t.output = {**t.output, **output}
            if error:
                t.error = error[:300]
    db.flush()


def cancel_old(db: Session, m: Mission) -> None:
    db.execute(update(MissionTask).where(MissionTask.mission_id == m.id, MissionTask.revision < m.revision, MissionTask.status.in_(["QUEUED", "RUNNING", "BLOCKED"])).values(status="CANCELLED"))


def compile_plan(db: Session, m: Mission, actions: list[Action], read_tasks: dict[str, MissionTask], policy_count: int) -> list[dict]:
    """Build the DAG for this revision: plan-phase tasks (done), one write task per action (+ verify task), and the final report task."""
    cancel_old(db, m)
    base = [t.id for t in read_tasks.values()]
    router = add(db, m, "route_domains", "domain_router", status="DONE", output={"domains": m.domains, "scenario": m.scenario}, timeout_ms=1000)
    ent = add(db, m, "resolve_entities", "entity_resolver", status="DONE", depends_on=[router.id], output={"bindings": {k: v for k, v in m.bindings.items()}}, timeout_ms=1000)
    pol = add(db, m, "evaluate_risk", "policy", status="DONE", depends_on=[ent.id], output={"actions_evaluated": policy_count, "approval_required": True}, timeout_ms=1000)
    ev = add(db, m, "gather_evidence", "evidence", status="DONE", depends_on=[ent.id] + base, output={"read_tasks": len(base)}, timeout_ms=1000)
    by_action: dict[str, MissionTask] = {}
    verify_ids = []
    for a in actions:
        dep = [pol.id, ev.id] + [by_action[d].id for d in (a.depends_on or []) if d in by_action]
        w = add(db, m, a.kind, "executor", "write", dep, "QUEUED", {"target": a.target_entity_id, "digest": a.digest[:12], "idempotency_key": a.idempotency_key}, None, a.id, 60000, 0)
        by_action[a.id] = w
        v = add(db, m, f"verify:{a.kind}", "verifier", "read", [w.id], "QUEUED", {}, None, a.id, 15000, 1)
        v.mode = "read"
        verify_ids.append(v.id)
    add(db, m, "final_receipt", "evidence", "read", verify_ids or [ev.id], "QUEUED", {}, None, None, 5000, 0)
    return view(db, m)


def view(db: Session, m: Mission) -> list[dict]:
    rows = list(db.scalars(select(MissionTask).where(MissionTask.mission_id == m.id).order_by(MissionTask.created_at, MissionTask.id)))
    return [{"id": t.id, "revision": t.revision, "kind": t.kind, "owner": t.owner, "mode": t.mode, "depends_on": t.depends_on, "status": t.status, "action_id": t.action_id,
             "attempts": t.attempts, "retry_budget": t.retry_budget, "timeout_ms": t.timeout_ms, "error": t.error, "output": t.output, "input": t.input,
             "started_at": t.started_at.isoformat() if t.started_at else None, "finished_at": t.finished_at.isoformat() if t.finished_at else None} for t in rows]
