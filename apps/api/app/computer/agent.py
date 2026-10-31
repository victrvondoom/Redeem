"""The closed loop: OBSERVE -> UNDERSTAND -> PLAN -> GROUND -> ACT -> OBSERVE AGAIN -> VERIFY -> CONTINUE.

Planning here is rule-based over what is actually on the screen (OCR text and positions, window list). No language
or vision model is configured in this deployment (see docs/REDEEM_REAL_COMPUTER_EXECUTION_REPORT.md), so requests
outside the supported intents are answered with NEEDS_INPUT instead of a guess. Every step re-reads the screen, so
after a pause, a takeover or an unexpected page the plan is rebuilt from the current state."""
from __future__ import annotations

import datetime as dt
import re
import threading
import time

from sqlalchemy import select

from ..db import SessionLocal, utcnow
from ..models import Case, ComputerFrame, ComputerSession, ComputerTask, DemoCrmContact, Document, PortalSubmission
from . import demo_crm, portal
from . import grounding as G
from .pipeline import Refused, perform

METHODS = {"whatsapp": "WhatsApp", "email": "Email", "e-mail": "Email", "phone": "Phone", "call": "Phone", "sms": "SMS", "text message": "SMS"}


class Stopped(Exception):
    pass


class Replan(Exception):
    pass


class Missing(Exception):
    pass


class BadParams(ValueError):
    pass


def supports(kind: str) -> bool:
    """True if this agent really implements the intent (used by the scenario catalog to report runnable vs not built)."""
    return hasattr(Loop, f"do_{kind}") and kind not in ("unsupported",)


def intent_for(kind: str, params: dict, tenant_id: str, db) -> dict:
    """Turn validated scenario parameters into the intent the loop executes. Values come from the caller or the caller's own records."""
    if kind == "crm_update":
        fu = {"date": params["followup_date"], "time": params.get("followup_time", "10:00")} if params.get("followup_date") else None
        return {"kind": kind, "name": params["name"], "method": params.get("method"), "followup": fu, "draft": params.get("draft") or None, "send": bool(params.get("send"))}
    if kind == "portal_case":
        c = db.scalar(select(Case).where(Case.id == params["case_id"], Case.tenant_id == tenant_id))  # tenant filter: another workspace's case is "not found"
        if not c:
            raise BadParams("Case not found in this workspace")
        docs = [d.filename for d in db.scalars(select(Document).where(Document.case_id == c.id, Document.tenant_id == tenant_id).order_by(Document.created_at))]
        amount = f"{c.claimed_paise / 100:.2f}".rstrip("0").rstrip(".") if c.claimed_paise else ""  # unknown stays empty; never guessed
        summary = c.title + (f" ({c.provider})" if c.provider else "")
        return {"kind": kind, "case_id": c.id, "payload": portal.payload(c.id, params.get("department", "Customer Relations"), summary, amount, docs[:5])}
    raise BadParams(f"{kind} cannot be started from a scenario")


def parse(instruction: str) -> dict:
    t = instruction.strip()
    lo = t.lower()
    if "crm" in lo:
        name = re.search(r"\b(?i:find|open|search for)\s+(?:the record (?:of|for)\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", t) or re.search(r"\bfor\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", t)
        method = next((v for k, v in METHODS.items() if re.search(rf"\b{k}\b", lo)), None)
        tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lo)
        hh = (int(tm.group(1)) % 12 + (12 if tm.group(3) == "pm" else 0)) if tm else 10
        when = dt.date.today() + dt.timedelta(days=1 if "tomorrow" in lo or not re.search(r"\btoday\b", lo) else 0)
        quoted = re.search(r"[\"“](.+?)[\"”]", t)
        first = name.group(1).split()[0] if name else "there"
        return {"kind": "crm_update", "name": name.group(1) if name else None, "method": method,
                "followup": {"date": when.isoformat(), "time": f"{hh:02d}:{(tm.group(2) if tm and tm.group(2) else '00')}"} if "follow" in lo else None,
                "draft": (quoted.group(1) if quoted else f"Hi {first}, following up on our conversation. I will call you on {when.isoformat()}.") if "draft" in lo or "message" in lo else None,
                "send": bool(re.search(r"\bsend\b", lo)) and not re.search(r"(do not|don't|dont|never) send|without sending", lo)}
    if re.search(r"\b(what('s| is) on (my|the) screen|explain (my|the|this) screen|describe (my|the) screen)\b", lo):
        return {"kind": "describe"}
    m = re.match(r"(?:please\s+)?open\s+(https?://\S+)", t, re.I)
    if m:
        return {"kind": "open_url", "url": m.group(1)}
    m = re.match(r"(?:please\s+)?(?:open|launch|start)\s+(chrome|edge|the browser|browser|notepad|file explorer|explorer|vs ?code|calculator)\b", lo)
    if m:
        app = {"chrome": "browser", "edge": "browser", "the browser": "browser", "browser": "browser", "file explorer": "explorer", "vscode": "vscode", "vs code": "vscode"}.get(m.group(1), m.group(1))
        return {"kind": "launch", "app": app}
    m = re.match(r"(?:please\s+)?click(?: on)?(?: the)?\s+(.+?)(?:\s+button)?\.?$", t, re.I)
    if m:
        return {"kind": "click", "label": m.group(1).strip("'\" ")}
    m = re.match(r"(?:please\s+)?type\s+[\"“]?(.+?)[\"”]?\.?$", t, re.I)
    if m:
        return {"kind": "type", "text": m.group(1)}
    m = re.match(r"(?:please\s+)?press\s+([a-z0-9+ ]+)\.?$", lo)
    if m:
        return {"kind": "key", "combo": m.group(1).replace(" ", "")}
    return {"kind": "unsupported"}


class Loop:
    def __init__(self, task_id: str):
        self.db = SessionLocal()
        self.task = self.db.get(ComputerTask, task_id)
        self.s = self.db.get(ComputerSession, self.task.session_id)
        self.epoch = self.s.control_epoch
        self.log: list[dict] = []
        self.frame: ComputerFrame | None = None

    # ------------------------------------------------------------ control
    def note(self, step: str, **kw):
        self.task.step = step[:80]
        self.log.append({"step": step, "at": utcnow().isoformat(), **kw})
        self.task.report = {**(self.task.report or {}), "log": self.log[-60:]}
        self.db.commit()

    def ctl(self):
        """Respect pause / takeover / stop. Returns True if control came back, meaning the plan must be rebuilt."""
        self.db.refresh(self.s)
        resumed = False
        t0 = time.time()
        while self.s.status in ("PAUSED", "USER_CONTROL"):
            if self.task.status != self.s.status:
                self.task.status = self.s.status
                self.note("paused" if self.s.status == "PAUSED" else "you have control; waiting")
            if time.time() - t0 > 1800:
                raise Stopped("waited 30 minutes for control to return")
            time.sleep(0.4)
            self.db.refresh(self.s)
            resumed = True
        if self.s.status in ("STOPPED", "ENDED"):
            raise Stopped(f"session {self.s.status.lower()}")
        if resumed or self.epoch != self.s.control_epoch:
            self.epoch = self.s.control_epoch
            self.task.status = "RUNNING"
            self.note("control returned: observing the current screen again")
            return True
        return False

    def act(self, action, params, reason, target=None, approved=None):
        if self.ctl():
            raise Replan()
        try:
            row, res = perform(self.db, self.s, action, params, task=self.task, reason=reason, target=target, epoch=self.epoch, approved_digest=approved)
        except Refused as e:
            if e.code in ("control_changed", "not_in_control", "stale_target"):
                raise Replan() from e
            raise
        if res.get("frame_id"):
            self.frame = self.db.get(ComputerFrame, res["frame_id"])
        if not res.get("ok"):
            if res.get("error") in ("paused", "user_has_control", "stopped"):
                raise Replan()
            raise Missing(f"{action} failed on the device: {res.get('error')} {res.get('detail', '')}")
        return row, res

    def observe(self):
        self.act("observe_screen", {}, "look at the screen")
        return self.frame

    def ground(self, label, tries=3, lowest=False):
        for i in range(tries):
            f = self.frame if i == 0 and self.frame and self.frame.id == self.s.latest_frame_id else self.observe()
            t = G.find(f, label, lowest=lowest)
            if t:
                return t
            time.sleep(0.6)
        raise Missing(f"could not find '{label}' on the screen")

    def click(self, label, reason, lowest=False, approved=None):
        t = self.ground(label, lowest=lowest)
        self.act("click_element", {"x": t["x"], "y": t["y"]}, reason, target=t, approved=approved)
        return t

    def type(self, text, reason):
        self.act("type_text", {"text": text}, reason)

    def expect(self, phrase, timeout=8.0) -> dict:
        end = time.time() + timeout
        while True:
            f = self.observe()
            if G.has(f, phrase):
                v = {"expected": phrase, "observed": True, "frame_id": f.id}
                self.note(f"verified: {phrase}", verification=v)
                return v
            if time.time() > end:
                v = {"expected": phrase, "observed": False, "frame_id": f.id}
                self.note(f"not verified: {phrase}", verification=v)
                return v
            time.sleep(0.7)

    def expect_fuzzy(self, phrase, timeout=4.0) -> dict:
        end = time.time() + timeout
        while True:
            f = self.observe()
            ok = G.has_fuzzy(f, phrase)
            if ok or time.time() > end:
                v = {"expected": phrase, "observed": ok, "frame_id": f.id, "method": "ocr_fuzzy"}
                self.note(("verified: " if ok else "not verified: ") + phrase[:40], verification=v)
                return v
            time.sleep(0.7)

    # ------------------------------------------------------------ intents
    def run(self):
        pre = self.task.intent or {}
        it = pre if (self.task.scenario_id and pre.get("kind")) else parse(self.task.instruction)  # scenario runs carry validated parameters
        self.task.intent, self.task.status = it, "RUNNING"
        self.note("understood the request", intent=it)
        try:
            getattr(self, f"do_{it['kind']}")(it)
        except Stopped as e:
            self.finish("STOPPED", f"Stopped: {e}. Nothing further was sent to the computer.")
        except Missing as e:
            self.finish("FAILED", f"Could not finish: {e}. The screen was left as it is; check it before trying again.")
        except Refused as e:
            if e.code == "approval_required":
                self.finish("NEEDS_APPROVAL", e.detail)
            else:
                self.finish("UNCERTAIN" if e.code == "device_unreachable" else "FAILED", f"{e.code}: {e.detail}")
        except Exception as e:  # noqa: BLE001 - never turn an exception into success
            self.finish("FAILED", f"{type(e).__name__}: {e}"[:300])
        finally:
            self.db.close()

    def finish(self, status, summary, **extra):
        self.task.status = status
        self.task.report = {**(self.task.report or {}), "summary": summary, "log": self.log[-60:], **extra}
        self.db.commit()

    def do_unsupported(self, it):
        self.finish("NEEDS_INPUT", "I can't plan that request yet. No vision or language model is configured, so REDEEM only runs these on a computer: "
                    "open a browser, Notepad or File Explorer, open a URL, click a visible label, type text, press a key, describe the screen, and the CRM update.")

    def do_describe(self, it):
        f = self.observe()
        lines = [ln for ln in G.texts(f).splitlines() if ln.strip()][:30]
        w = (f.active_window or {})
        self.finish("DONE", f"Active window: {w.get('title') or w.get('app') or 'unknown'}. Text read from the screen (OCR, not interpretation): " + " | ".join(lines[:12]),
                    screen_text=lines, frame_id=f.id)

    def do_launch(self, it):
        before = self.observe().sha256
        self.act("launch_application", {"app": it["app"]}, f"open {it['app']}")
        time.sleep(2.5)
        f = self.observe()
        w = (f.active_window or {})
        self.finish("DONE" if f.sha256 != before else "UNCERTAIN", f"Opened {it['app']}. Active window now: {w.get('title') or w.get('app') or 'unknown'}"
                    + ("" if f.sha256 != before else " (the screen did not change, so this is not confirmed)") + ".", frame_id=f.id)

    def approved(self):
        return (self.task.pending_approval or {}).get("approved_digest")

    def do_open_url(self, it):
        self.act("open_url", {"url": it["url"]}, "open the requested page")
        time.sleep(3)
        f = self.observe()
        host = re.sub(r"^https?://([^/]+).*", r"\1", it["url"])
        ok = G.has(f, host.split(":")[0])
        self.finish("DONE" if ok else "UNCERTAIN", f"Opened {it['url']}; address {'seen' if ok else 'not confirmed'} on screen.", frame_id=f.id)

    def do_click(self, it):
        before = self.observe()
        t = self.click(it["label"], f"click '{it['label']}' as asked")
        changed = self.frame.sha256 != before.sha256
        self.finish("DONE" if changed else "UNCERTAIN", f"Clicked '{t['text']}' at ({t['x']}, {t['y']}). The screen {'changed' if changed else 'did not visibly change'}.", target=t)

    def do_type(self, it):
        self.type(it["text"], "type the requested text")
        v = self.expect(it["text"][:30], timeout=3)
        self.finish("DONE" if v["observed"] else "UNCERTAIN", f"Typed {len(it['text'])} characters; {'visible on screen' if v['observed'] else 'not confirmed on screen'}.")

    def do_key(self, it):
        self.act("key_combination", {"combo": it["combo"]}, "press the requested keys")
        self.finish("DONE", f"Pressed {it['combo']}.")

    # ------------------------------------------------------------ CRM scenario (operates the CRM's UI; no API shortcut)
    def do_crm_update(self, it):
        if not it.get("name"):
            return self.finish("NEEDS_INPUT", "Which customer should I open? Say: find <first name> <last name>.")
        key = demo_crm.ensure(self.db, self.task.tenant_id)
        base = self._crm_base(key)
        name, method, fu, draft = it["name"], it.get("method"), it.get("followup"), it.get("draft")
        done = {"method": not method, "followup": not fu, "draft": not draft}
        checks: list[dict] = []
        for _ in range(30):
            try:
                if self.ctl():
                    continue
                f = self.observe()
                if not G.has(f, "Demo CRM"):
                    self.note("CRM not on screen: opening it")
                    self.act("open_url", {"url": base}, "open the CRM")
                    self.expect("Customers", timeout=12)
                    continue
                on_record = G.has(f, "Contact record") or (G.has(f, "Preferred contact method") and G.has(f, "Follow-ups"))
                heading = G.find(f, "Customers")
                on_list = not on_record and bool(heading) and heading["match"] == 3
                if on_record and G.has(f, name):
                    if not done["method"]:
                        if G.has(f, f"Current preferred contact: {method}"):
                            done["method"] = True
                            continue
                        self.click(method, f"choose {method} as the preferred contact method")
                        self.click("Save contact", "save the contact record")
                        checks.append(self.expect(f"Current preferred contact: {method}"))
                        done["method"] = checks[-1]["observed"]
                        continue
                    if not done["followup"]:
                        if G.has(f, f"Follow-up {fu['date']} {fu['time']}"):
                            done["followup"] = True
                            continue
                        self.click("Follow-up date", "focus the follow-up date field")
                        self.type(fu["date"], "enter the follow-up date")
                        self.click("Time", "focus the follow-up time field")
                        self.type(fu["time"], "enter the follow-up time")
                        self.click("Add follow-up", "add the follow-up")
                        checks.append(self.expect(f"Follow-up {fu['date']} {fu['time']}"))
                        done["followup"] = checks[-1]["observed"]
                        continue
                    if not done["draft"]:
                        if G.has(f, "Draft: " + draft[:20]):
                            done["draft"] = True
                            continue
                        self.click("Write the message draft", "focus the draft box")
                        self.type(draft, "write the message draft")
                        self.click("Save draft", "save the draft (not send)")
                        checks.append(self.expect("Draft saved"))
                        done["draft"] = checks[-1]["observed"]
                        continue
                    if it.get("send") and not done.get("send"):
                        self.click("Send message", "send the message (needs your approval)", approved=self.approved())
                        checks.append(self.expect("Message sent"))
                        done["send"] = checks[-1]["observed"]
                        continue
                    break
                if on_record:
                    self.click("All customers", "wrong record open: go back to the list")
                    continue
                if on_list:
                    if G.find(f, name, lowest=True) and G.find(f, name, lowest=True)["y"] > (G.find(f, "Customers") or {"y": 0})["y"] + 60:
                        self.click(name, f"open {name}'s record", lowest=True)
                        self.expect(f"Contact record: {name}")
                        continue
                    anchor = G.find(f, "Search customers") or G.find(f, "Customers")
                    pt = {**anchor, "label": "search box", "y": anchor["y"] + (0 if anchor["text"].lower().startswith("search") else 44)}
                    self.act("click_element", {"x": pt["x"], "y": pt["y"]}, "focus the customer search box", target=pt)
                    self.act("key_combination", {"combo": "ctrl+a"}, "select any old search text")
                    self.type(name, f"search for {name}")
                    self.expect(name)
                    continue
                self.note("unexpected screen: observing again")
            except Replan:
                self.note("state changed: re-planning from the current screen")
                continue
        if not all(done.values()):
            return self.finish("FAILED", "Could not complete every step; see the timeline for the last verified state.", checks=checks, done=done)
        # persistence check through the UI: reload and read the values back off the screen
        self.act("key_combination", {"combo": "f5"}, "reload the record to confirm the values were saved")
        reload_checks = [self.expect(p, timeout=10) for p in ([f"Current preferred contact: {method}"] if method else []) +
                         ([f"Follow-up {fu['date']} {fu['time']}"] if fu else []) + (["Draft: " + draft[:20]] if draft else []) + ([] if it.get("send") else ["No messages sent"])]
        # independent read-only check of the application's stored state (not used to change anything)
        c = self.db.scalar(select(DemoCrmContact).where(DemoCrmContact.workspace_key == key, DemoCrmContact.name == name))
        stored = {"preferred_contact": c.preferred_contact, "followups": c.followups[-1:] if c else [], "drafts": len(c.drafts) if c else 0, "sent": len(c.sent) if c else None}
        ok = all(x["observed"] for x in reload_checks) and c and (not method or c.preferred_contact == method) and (bool(c.sent) if it.get("send") else not c.sent)
        summary = (f"Updated {name}: preferred contact {method or 'unchanged'}" + (f", follow-up {fu['date']} {fu['time']}" if fu else "") +
                   (", draft saved" if draft else "") + (". The message was sent (simulated demo send) after your approval." if it.get("send") and c and c.sent else ". The message was NOT sent.") + ("" if ok else " Some values could not be confirmed after reload."))
        self.finish("DONE" if ok else "UNCERTAIN", summary, checks=checks, after_reload=reload_checks, stored_state=stored)

    # ------------------------------------------------------------ consumer case via the REDEEM-owned portal
    def do_portal_case(self, it):
        p = it["payload"]
        key = portal.workspace_key(self.db, self.task.tenant_id)
        dg = portal.payload_digest(p)
        base = (self._crm_base(key)).replace("/demo/crm/", "/portal/")

        def stored():
            self.db.expire_all()
            return self.db.scalar(select(PortalSubmission).where(PortalSubmission.workspace_key == key, PortalSubmission.payload_digest == dg))
        if stored():  # reconcile, never resend
            r = stored()
            return self.finish("DONE", f"This exact request was already received by the REDEEM case portal as {r.acknowledgement_id}. Nothing was submitted again.", acknowledgement_id=r.acknowledgement_id)
        fields = [("Case reference", p["case_ref"], 38), ("Claim summary", p["claim_summary"], 38), ("Amount claimed in INR", p["amount_inr"], 38), ("Supporting documents", ", ".join(p["documents"]), 38)]
        for _ in range(40):
            try:
                if self.ctl():
                    continue
                f = self.observe()
                if not G.has(f, "Case request form"):
                    self.note("portal not on screen: opening it")
                    self.act("open_url", {"url": base}, "open the REDEEM case portal")
                    self.expect("Case request form", timeout=12)
                    continue
                todo = next(((lab, val, dy) for lab, val, dy in fields if val and not G.has_fuzzy(f, val[:30])), None)
                if todo:
                    lab, val, dy = todo
                    h = G.find(f, lab)
                    if not h:
                        raise Missing(f"could not find the '{lab}' field")
                    self.act("click_element", {"x": h["x"], "y": h["y"] + dy}, f"focus the '{lab}' field", target={**h, "label": lab})
                    self.type(val, f"enter {lab}")
                    self.expect_fuzzy(val[:30], timeout=4)
                    continue
                if not G.has(f, f"Selected department: {p['department']}"):
                    self.click(p["department"], f"choose the {p['department']} department")
                    self.expect(f"Selected department: {p['department']}", timeout=4)
                    continue
                break  # every field is visible on screen with the intended value
            except Replan:
                self.note("state changed: re-planning from the current screen")
        else:
            return self.finish("FAILED", "Could not fill the form completely; nothing was submitted.")
        shown = self.observe()
        t = self.ground("Submit request")
        t = {**t, "label": f"Submit request [payload {dg[:16]}]"}  # the approval digest covers the label, so it is bound to this exact payload
        try:
            self.act("click_element", {"x": t["x"], "y": t["y"]}, "submit the completed request (needs your approval of the exact values)", target=t, approved=self.approved())
        except Refused as e:
            if e.code == "approval_required":
                self.task.pending_approval = {**(self.task.pending_approval or {}), "payload": p, "payload_digest": dg, "form_frame_id": shown.id,
                                              "portal": "REDEEM case portal (first-party; not an external filing)"}
                self.db.commit()
            raise
        for _ in range(10):
            time.sleep(0.8)
            if stored():
                break
        r = stored()
        if not r:
            return self.finish("UNCERTAIN", "I clicked Submit but could not find a stored submission. I will not submit again; check the portal.", payload_digest=dg)
        r.approval_ref = self.approved()
        self.db.commit()
        seen = G.has(self.observe(), r.acknowledgement_id)
        ok = r.payload_digest == dg
        self.finish("DONE" if ok else "UNCERTAIN", f"Submitted to the REDEEM case portal (a first-party system, not an external filing). Acknowledgement {r.acknowledgement_id}"
                    + (" is shown on screen" if seen else " was stored but could not be read on screen") + ". The stored submission was retrieved independently and "
                    + ("matches the approved values." if ok else "DOES NOT match the approved values."),
                    acknowledgement_id=r.acknowledgement_id, submission_id=r.id, payload_digest=dg, checks=[{"expected": "acknowledgement on screen", "observed": seen}, {"expected": "stored payload equals approved payload", "observed": ok}])

    def _crm_base(self, key):
        import os
        return (os.environ.get("REDEEM_PUBLIC_API_URL") or "http://127.0.0.1:8000").rstrip("/") + f"/demo/crm/{key}/"


def start(task_id: str) -> None:
    threading.Thread(target=lambda: Loop(task_id).run(), name=f"computer-task-{task_id}", daemon=True).start()
