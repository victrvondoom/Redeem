"""Recorded browser skills (inherited from RESOLVE's "skills" idea, rebuilt on REDEEM's BrowserRun).

A skill is *recorded by doing*: its steps are executed once in a real, isolated Chromium session against the
allow-listed apps, and it is saved only if every step succeeded. A replay runs the same steps in a fresh session,
captures a screenshot after each step, honours pause/resume/stop between steps, stops at any step only the user
may perform (login, CAPTCHA, OTP, payment) and never retries automatically: if a run fails after a click it is
marked ``uncertain`` so the user checks the app before running it again (reconcile-not-resend).
"""
from __future__ import annotations

import re
import threading
import time

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import BrowserSkill, BrowserSkillRun
from . import browser as rb

OPS = {"goto", "fill", "click", "wait_text"}
APPS = {"crm", "docs", "outbox"}
_PARAM = re.compile(r"\{\{\s*([a-z_][a-z0-9_]{0,30})\s*\}\}")
_CONTROL: dict[str, str] = {}  # run_id -> "pause" | "stop"; process-local (single API instance), see docs/OPEN_BLOCKERS.md
_LOCK = threading.Lock()


class SkillError(ValueError):
    pass


def validate_steps(steps: list[dict]) -> tuple[list[dict], list[str]]:
    if not 1 <= len(steps) <= 25:
        raise SkillError("a skill needs 1 to 25 steps")
    out, params = [], []
    for i, s in enumerate(steps):
        op = s.get("op")
        if op not in OPS:
            raise SkillError(f"step {i + 1}: unknown op {op!r}")
        if op == "goto":
            app, path = s.get("app"), str(s.get("path") or "/")
            if app not in APPS:
                raise SkillError(f"step {i + 1}: app must be one of {sorted(APPS)}")
            if not path.startswith("/") or "//" in path or ".." in path or len(path) > 120:
                raise SkillError(f"step {i + 1}: path must be a simple absolute path on the app")
            out.append({"op": op, "app": app, "path": path})
            continue
        key = {"fill": "label", "click": "button", "wait_text": "text"}[op]
        tgt = str(s.get(key) or "").strip()
        if not tgt or len(tgt) > 80:
            raise SkillError(f"step {i + 1}: {key} is required (max 80 chars)")
        st = {"op": op, key: tgt}
        if op == "fill":
            st["value"] = str(s.get("value") or "")[:500]
            params += _PARAM.findall(st["value"])
        out.append(st)
    if out[0]["op"] != "goto":
        raise SkillError("the first step must open an app (goto)")
    return out, sorted(set(params))


def substitute(value: str, params: dict) -> str:
    def rep(m):
        k = m.group(1)
        if k not in params or params[k] in (None, ""):
            raise SkillError(f"missing parameter {k!r}")
        return str(params[k])[:500]
    return _PARAM.sub(rep, value)


def control(run_id: str, action: str) -> None:
    with _LOCK:
        if action == "resume":
            _CONTROL.pop(run_id, None)
        else:
            _CONTROL[run_id] = action


def _gate(db: Session, run: BrowserSkillRun) -> None:
    while True:
        with _LOCK:
            c = _CONTROL.get(run.id)
        if c == "stop":
            raise rb.RunStopped()
        if c != "pause":
            if run.status == "PAUSED":
                run.status = "RUNNING"
                db.commit()
            return
        if run.status != "PAUSED":
            run.status = "PAUSED"
            db.commit()
        time.sleep(0.2)


def execute(db: Session, run: BrowserSkillRun, steps: list[dict], params: dict, step_delay: float = 0.0) -> BrowserSkillRun:
    w = rb.world_for(run.tenant_id)
    origin = {"crm": w.crm.url, "docs": w.docs.url, "outbox": w.outbox.url}
    run.status, run.total_steps = "RUNNING", len(steps)
    db.commit()
    clicked = False
    try:
        with rb.BrowserRun(db, run.tenant_id, w, None, run.id) as br:
            run.session_id = br.row.id
            db.commit()
            page = br.page()
            for i, s in enumerate(steps):
                _gate(db, run)
                if s["op"] == "goto":
                    page.goto(origin[s["app"]] + s["path"])
                    page.wait_for_load_state("networkidle")
                else:
                    br.guard_user_only(page)
                    br.dismiss_popups(page)
                    if s["op"] == "fill":
                        br.fill_first(page, [s["label"]], substitute(s["value"], params))
                    elif s["op"] == "click":
                        clicked = True
                        br.click_first(page, [s["button"]])
                    else:
                        page.get_by_text(s["text"]).first.wait_for(timeout=8000)
                br.guard_user_only(page)
                phase = "before" if i == 0 else ("after" if i == len(steps) - 1 else "observe")
                br.snapshot(page, phase, f"step {i + 1}: {s['op']}")
                run.step_index = i + 1
                db.commit()
                if step_delay:
                    time.sleep(step_delay)
        run.status = "DONE"
    except rb.UserActionRequired as e:
        run.status, run.error = "USER_ACTION_REQUIRED", f"{e.reason} at {e.detail}"[:300]
    except rb.RunStopped:
        run.status, run.error, run.uncertain = "STOPPED", "stopped by user", clicked
    except Exception as e:  # noqa: BLE001 - a real browser can fail in many ways; the run records it
        run.status, run.error, run.uncertain = "FAILED", f"step {run.step_index + 1}: {type(e).__name__}: {str(e)[:200]}", clicked
    finally:
        with _LOCK:
            _CONTROL.pop(run.id, None)
    if run.skill_id:
        sk = db.get(BrowserSkill, run.skill_id)
        if sk:
            sk.runs, sk.last_status = sk.runs + 1, run.status
    db.commit()
    return run


def execute_in_background(run_id: str, steps: list[dict], params: dict, step_delay: float = 0.6) -> None:
    def work():
        with SessionLocal() as db:
            run = db.get(BrowserSkillRun, run_id)
            if run:
                execute(db, run, steps, params, step_delay)
    threading.Thread(target=work, name=f"skill-{run_id}", daemon=True).start()
