"""Scenario catalog: validation of typed step definitions, built-in seeding, version snapshots and run-status derivation.

A scenario never contains executable code. `steps` is a list of {"op": <approved operation>, ...} descriptions drawn from
STEP_OPS, and `executor` names an agent intent that already exists in app/computer/agent.py. Status shown to people is
derived from the persisted `computer_tasks` rows; nothing here stores a status."""
from __future__ import annotations

import jsonschema
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ComputerScenario, ComputerScenarioVersion, ComputerTask
from . import protocol as P

# Approved typed operations. Physical ops reuse the bridge protocol; the rest are agent-level checks.
LOGICAL_OPS = {"verify_text", "verify_state", "request_approval", "read_back_stored_state", "locate_file", "move_file", "inspect_pdf", "note", "replan"}
STEP_OPS = (P.INPUT | P.READ) | LOGICAL_OPS
OS_VALUES = {"any", "windows", "linux", "macos"}
CAPABILITIES = {"screen_observation", "mouse", "keyboard", "launch_application", "open_url", "ocr", "file_system_read", "file_system_write", "approval"}
RUN_STATUS = {"PLANNING": "queued", "RUNNING": "running", "PAUSED": "paused", "USER_CONTROL": "paused", "NEEDS_APPROVAL": "waiting_for_approval", "DONE": "completed",
              "FAILED": "failed", "STOPPED": "cancelled", "UNCERTAIN": "outcome_uncertain", "NEEDS_INPUT": "needs_input"}

BUILTIN: list[dict] = [
    dict(key="crm-operator", name="CRM operator", category="crm", executor="crm_update", required_os="any",
         description="Open the demo CRM in a browser, find a customer, set the preferred contact method, add a follow-up and save a message draft. Sending needs approval.",
         required_capabilities=["screen_observation", "mouse", "keyboard", "open_url", "ocr", "approval"],
         parameter_schema={"type": "object", "required": ["name"], "additionalProperties": False, "properties": {
             "name": {"type": "string", "minLength": 3, "maxLength": 80}, "method": {"enum": ["WhatsApp", "Email", "Phone", "SMS"]},
             "followup_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}, "followup_time": {"type": "string", "pattern": r"^\d{1,2}:\d{2}$"},
             "draft": {"type": "string", "maxLength": 1000}, "send": {"type": "boolean"}}},
         steps=[{"op": "open_url", "target": "demo CRM"}, {"op": "find_element", "target": "customer record"}, {"op": "click_element", "target": "preferred contact method"},
                {"op": "type_text", "target": "follow-up date and time"}, {"op": "type_text", "target": "message draft"}, {"op": "request_approval", "target": "Send message", "when": "only if send=true"},
                {"op": "key_combination", "keys": "f5"}, {"op": "verify_text", "target": "values after reload"}, {"op": "read_back_stored_state", "target": "CRM record"}],
         expected_result="The customer record shows the chosen contact method, follow-up and draft after a reload, and no message was sent unless approved.",
         verification=["values read back from the screen after reload", "independent read of the CRM's stored record"], approvals=["Send message (exact action)"]),
    dict(key="file-explorer-pdf", name="Find, move and inspect a PDF", category="files", executor="files_pdf", required_os="windows",
         description="Locate a PDF in an authorized folder, move it to an authorized destination, open it and confirm its identity. NOT RUNNABLE YET: needs bridge file operations and interactive Windows validation.",
         required_capabilities=["screen_observation", "mouse", "keyboard", "launch_application", "file_system_read", "file_system_write", "approval"],
         parameter_schema={"type": "object", "required": ["file_name", "source_dir", "destination_dir"], "additionalProperties": False, "properties": {
             "file_name": {"type": "string", "maxLength": 200}, "source_dir": {"type": "string", "maxLength": 300}, "destination_dir": {"type": "string", "maxLength": 300}}},
         steps=[{"op": "launch_application", "app": "explorer"}, {"op": "locate_file", "target": "file_name in source_dir"}, {"op": "request_approval", "target": "move or overwrite"},
                {"op": "move_file", "target": "destination_dir"}, {"op": "launch_application", "app": "browser"}, {"op": "inspect_pdf", "target": "moved file"}, {"op": "verify_state", "target": "source gone, destination present"}],
         expected_result="The file exists at the destination (same SHA-256 as before), is gone from the source, and the opened document matches.",
         verification=["SHA-256 before and after", "source/destination listing", "rendered document text"], approvals=["Overwrite or replace", "Move"]),
    dict(key="consumer-case-portal", name="Consumer case via the REDEEM case portal", category="cases", executor="portal_case", required_os="any",
         description="Open the REDEEM-owned case portal, fill the form from a real case in this workspace, show it for approval, submit and read back the stored acknowledgement. This is a first-party portal, not an external filing.",
         required_capabilities=["screen_observation", "mouse", "keyboard", "open_url", "ocr", "approval"],
         parameter_schema={"type": "object", "required": ["case_id"], "additionalProperties": False, "properties": {
             "case_id": {"type": "string", "minLength": 3, "maxLength": 40}, "department": {"enum": ["Customer Relations", "Billing", "Escalations"]}}},
         steps=[{"op": "open_url", "target": "REDEEM case portal"}, {"op": "type_text", "target": "case reference, department, summary, amount, documents"}, {"op": "request_approval", "target": "Submit request (exact payload)"},
                {"op": "click_element", "target": "Submit request"}, {"op": "verify_text", "target": "acknowledgement ID"}, {"op": "read_back_stored_state", "target": "portal submission"}],
         expected_result="A persisted portal submission exists whose acknowledgement ID matches the one shown on screen.",
         verification=["acknowledgement ID visible on screen", "stored submission retrieved independently"], approvals=["Submit request bound to the exact form values"]),
    dict(key="page-change-recovery", name="Recovery when the page changes", category="resilience", executor=None, required_os="any",
         description="Behaviour of the agent loop, not a runnable task: it detects a changed screen, discards the stale target and plans again.",
         required_capabilities=["screen_observation"], parameter_schema={"type": "object"}, steps=[{"op": "verify_state", "target": "screen changed"}, {"op": "replan"}],
         expected_result="No action is sent to a target found on an older frame.", verification=["stale_target refusal recorded"], approvals=[]),
    dict(key="user-takeover", name="User takeover", category="resilience", executor=None, required_os="any",
         description="Behaviour of the session controls, not a runnable task: pause, take control, hand back, agent re-observes.",
         required_capabilities=["screen_observation", "mouse", "keyboard"], parameter_schema={"type": "object"}, steps=[{"op": "note", "target": "pause"}, {"op": "replan"}],
         expected_result="The agent sends no input while the person has control and re-observes afterwards.", verification=["control epoch changes recorded"], approvals=[]),
]


class Invalid(ValueError):
    pass


def validate_definition(d: dict) -> dict:
    """Validate a scenario definition; returns the cleaned dict or raises Invalid."""
    out = {k: d[k] for k in ("key", "name", "description", "category", "required_capabilities", "required_os", "parameter_schema", "steps", "expected_result", "verification", "approvals", "executor") if k in d}
    if not out.get("key") or not all(c.isalnum() or c in "-_" for c in out["key"]) or len(out["key"]) > 60:
        raise Invalid("key must be 1-60 characters of letters, digits, - or _")
    if not str(out.get("name", "")).strip():
        raise Invalid("name is required")
    if out.get("required_os", "any") not in OS_VALUES:
        raise Invalid(f"required_os must be one of {sorted(OS_VALUES)}")
    bad = [c for c in out.get("required_capabilities", []) if c not in CAPABILITIES]
    if bad:
        raise Invalid(f"unknown capabilities {bad}; allowed {sorted(CAPABILITIES)}")
    for i, st in enumerate(out.get("steps", [])):
        if not isinstance(st, dict) or st.get("op") not in STEP_OPS:
            raise Invalid(f"step {i + 1}: op must be one of the approved operations")
        if set(st) - {"op", "target", "app", "keys", "when"} or any(not isinstance(v, str) or len(v) > 200 for v in st.values()):
            raise Invalid(f"step {i + 1}: only short text fields op/target/app/keys/when are allowed (no code)")
    try:
        jsonschema.Draft202012Validator.check_schema(out.get("parameter_schema", {}))
    except jsonschema.SchemaError as e:
        raise Invalid(f"parameter_schema is not a valid JSON Schema: {e.message}")
    if "pattern" in str(out.get("parameter_schema", {})) and len(str(out["parameter_schema"])) > 5000:
        raise Invalid("parameter_schema too large")
    if out.get("executor") is not None and not isinstance(out["executor"], str):
        raise Invalid("executor must be an agent intent name or null")
    return out


def check_params(sc: ComputerScenario, params: dict) -> dict:
    try:
        jsonschema.validate(params or {}, sc.parameter_schema or {"type": "object"})
    except jsonschema.ValidationError as e:
        raise Invalid(f"invalid parameters: {e.message}")
    return params or {}


def snapshot(sc: ComputerScenario) -> dict:
    return {k: getattr(sc, k) for k in ("key", "name", "description", "category", "required_capabilities", "required_os", "parameter_schema", "steps", "expected_result",
                                         "verification", "approvals", "executor", "version", "enabled")}


def record_version(db: Session, sc: ComputerScenario, who: str, reason: str) -> None:
    db.add(ComputerScenarioVersion(scenario_id=sc.id, version=sc.version, snapshot=snapshot(sc), changed_by=who, reason=reason[:300]))


def seed(db: Session) -> None:
    """Idempotently create built-in (global) entries. Existing rows are never overwritten, so administrator edits survive restarts."""
    have = {r for r in db.scalars(select(ComputerScenario.key).where(ComputerScenario.tenant_id.is_(None)))}
    for d in BUILTIN:
        if d["key"] in have:
            continue
        sc = ComputerScenario(tenant_id=None, created_by="system", **validate_definition(d))
        db.add(sc)
        db.flush()
        record_version(db, sc, "system", "built-in definition")
    db.commit()


def run_view(t: ComputerTask | None) -> dict | None:
    """Safe summary of a persisted task. Status/time/verification come only from the row."""
    if not t:
        return None
    rep = t.report or {}
    checks = rep.get("after_reload") or rep.get("checks") or []
    if t.status == "DONE":
        ver = "verified" if checks and all(c.get("observed") for c in checks) else "not_independently_verified"
    elif t.status == "UNCERTAIN":
        ver = "unverified"
    else:
        ver = None
    return {"task_id": t.id, "session_id": t.session_id, "status": RUN_STATUS.get(t.status, t.status.lower()), "raw_status": t.status, "started_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(), "completed_at": t.updated_at.isoformat() if t.status in ("DONE", "FAILED", "STOPPED", "UNCERTAIN") else None,
            "verification_status": ver, "summary": str(rep.get("summary", ""))[:300] or None}


def last_runs(db: Session, tenant_id: str, scs: list[ComputerScenario]) -> dict[str, list[ComputerTask]]:
    """Newest-first tasks per scenario id. Tasks started before the catalog existed match on intent kind == executor."""
    rows = list(db.scalars(select(ComputerTask).where(ComputerTask.tenant_id == tenant_id).order_by(ComputerTask.created_at.desc()).limit(500)))
    by_exec = {sc.executor: sc.id for sc in scs if sc.executor and sc.tenant_id is None}
    out: dict[str, list[ComputerTask]] = {sc.id: [] for sc in scs}
    for t in rows:
        sid = t.scenario_id or by_exec.get((t.intent or {}).get("kind"))
        if sid in out:
            out[sid].append(t)
    return out


