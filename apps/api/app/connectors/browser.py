"""Browser connector (RESOLVE's executor on REDEEM's mission engine). Actions run in a real Chromium against the tenant's simulated CRM / report store /
outbox. The UI's own toast is NEVER trusted: verification reads each app's API independently."""
import secrets
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FxFault
from ..resolve import browser as rb
from .base import ProviderRejected, ProviderTimeout, UserActionNeeded, canonical, sha256_hex


class BrowserConnector:
    name = "browser_fixture"

    def __init__(self, db: Session, tenant_id: str):
        self.db, self.tenant_id = db, tenant_id

    @property
    def world(self):
        return rb.world_for(self.tenant_id)

    def _take(self, kind: str) -> bool:
        f = self.db.scalar(select(FxFault).where(FxFault.tenant_id == self.tenant_id, FxFault.kind == kind, FxFault.remaining > 0))
        if not f:
            return False
        f.remaining -= 1
        self.db.flush()
        return True

    def _contact(self, cid: str) -> dict | None:
        return next((c for c in rb.get_json(self.world.crm.url + "/api/contacts") if c["id"] == cid), None)

    def version_hash(self, params: dict) -> str:
        """Temporal guard input: the exact state the human approved against (contact record; served bytes of the report)."""
        if params["kind_hint"] == "browser_crm_task":
            c = self._contact(params["contact_id"])
            if not c:
                raise ProviderRejected("contact_not_found")
            return sha256_hex(canonical([c, params["title"]]))
        c = self._contact(params["contact_id"])
        live = rb.report_bytes_sha(self.world, params["attachment_id"])
        if not c or not live:
            raise ProviderRejected("target_not_found")
        return sha256_hex(canonical([c["email"], live, params["to_addr"], params["attachment_sha256"]]))

    def snapshot(self, params: dict) -> dict:
        if params["kind_hint"] == "browser_crm_task":
            return {"tasks_before": len(rb.get_json(self.world.crm.url + "/api/tasks"))}
        return {"messages_before": len(rb.get_json(self.world.outbox.url + "/api/messages"))}

    def lookup(self, key: str):
        for t in rb.get_json(self.world.crm.url + "/api/tasks"):
            if t.get("op_id") == key:
                return SimpleNamespace(ref=t["id"], status="CREATED", kind="task")
        for m in rb.get_json(self.world.outbox.url + f"/api/messages?op_id={key}"):
            return SimpleNamespace(ref=m["id"], status="SENT_SIMULATED", kind="message")
        return None

    def submit(self, kind: str, params: dict, key: str | None) -> dict:
        key = key or f"nokey_{secrets.token_hex(6)}"
        from .base import ProviderRejected as PR  # noqa: F811
        from ..resolve.browser import CURRENT
        cur = CURRENT.get() or {}
        w = self.world
        silent = self._take("silent_drop") if kind == "browser_crm_task" else False      # each fault applies to the action it models
        lost = self._take("ack_loss") if kind == "browser_send_report" else False
        try:
            with rb.BrowserRun(self.db, self.tenant_id, w, cur.get("mission_id"), cur.get("action_id")) as br:
                if kind == "browser_crm_task":
                    if silent:
                        rb.set_fault(w, "crm", "misleading_toast")          # the app will SAY it worked and write nothing
                    page = br.page()
                    page.goto(w.crm.url)
                    br.guard_user_only(page)
                    br.dismiss_popups(page)
                    page.get_by_test_id("contact-row").first.wait_for(timeout=10000)
                    row = page.locator(f'[data-testid=contact-row][data-contact-id="{params["contact_id"]}"]')
                    if not row.count():
                        raise PR("contact_not_found", "contact is no longer on the page")
                    cells = row.locator("td").all_inner_texts()
                    if cells[2] != params["contact_email"]:                     # page-level temporal guard: identity must still match what was approved
                        raise PR("contact_changed", f"page shows {cells[2]!r}, approved {params['contact_email']!r}")
                    br.snapshot(page, "before", "crm before task", rb.get_json(w.crm.url + "/api/tasks"))
                    br.fill_first(page, ["Contact ID"], params["contact_id"])
                    br.fill_first(page, ["Task title", "Follow-up title"], params["title"])
                    page.evaluate("op => document.querySelector('#f [name=op_id]').value = op", key)
                    br.click_first(page, ["Create task", "Save follow-up"])
                    page.locator("#toast:not(:empty)").wait_for(timeout=8000)
                    toast = page.locator("#toast").inner_text()
                    page.reload()
                    page.get_by_test_id("contact-row").first.wait_for(timeout=10000)
                    br.snapshot(page, "after", "crm after task (reloaded: persisted state, not optimistic UI)", rb.get_json(w.crm.url + "/api/tasks"))
                    if not toast.startswith("Task created:"):
                        raise PR("ui_error", toast)
                    return {"ref": toast.split(": ", 1)[1], "status": "UI_REPORTED_CREATED", "ui_toast": toast, "fallbacks": br.fallbacks, "blocked_requests": len(br.blocked)}
                # send report through the outbox UI
                live = rb.report_bytes_sha(w, params["attachment_id"])
                if live != params["attachment_sha256"]:
                    raise PR("attachment_changed", "the report changed after you approved it")
                page = br.page()
                page.goto(w.outbox.url)
                br.guard_user_only(page)
                br.snapshot(page, "before", "outbox before send", rb.get_json(w.outbox.url + "/api/messages"))
                page.get_by_label("To").fill(params["to_addr"])
                page.get_by_label("Attachment ID").fill(params["attachment_id"])
                page.get_by_label("Attachment SHA-256").fill(params["attachment_sha256"])
                page.get_by_label("Body").fill(params["body"])
                page.evaluate("op => document.querySelector('#f [name=op_id]').value = op", key)
                if lost:
                    rb.set_fault(w, "outbox", "drop_ack")                       # committed, but the response never arrives
                page.get_by_role("button", name="Send (simulated)").click()
                page.locator("#toast:not(:empty)").wait_for(timeout=8000)
                ack = page.locator("#toast").inner_text()
                br.snapshot(page, "after", "outbox after send", rb.get_json(w.outbox.url + "/api/messages"))
                if not ack.startswith("Sent:"):
                    raise ProviderTimeout(ack)                                  # effect UNKNOWN: engine reconciles by lookup, never resends
                return {"ref": ack.split(": ", 1)[1], "status": "UI_REPORTED_SENT_SIMULATED", "ui_toast": ack, "fallbacks": br.fallbacks, "blocked_requests": len(br.blocked)}
        except rb.UserActionRequired as e:
            raise UserActionNeeded(e.reason, e.detail)
        except rb.StaleState as e:
            raise PR("stale_page", str(e))
        except (ProviderTimeout, ProviderRejected, UserActionNeeded):
            raise
        except Exception as e:                                                   # browser/page failure: effect unknown only if we may have clicked
            if "Timeout" in type(e).__name__:
                raise ProviderTimeout(f"browser timeout: {type(e).__name__}")
            raise PR("browser_error", f"{type(e).__name__}: {str(e)[:200]}")
        finally:
            w.crm.faults.pop("misleading_toast", None)

    def verify(self, kind: str, params: dict, idempotency_key: str, snapshot: dict) -> tuple[str, dict]:
        if kind == "browser_crm_task":
            tasks = rb.get_json(self.world.crm.url + "/api/tasks")
            same = [t for t in tasks if t["contact_id"] == params["contact_id"] and t["title"] == params["title"]]
            mine = [t for t in same if t.get("op_id") == idempotency_key]
            ev = {"tasks_before": snapshot.get("tasks_before"), "tasks_now": len(tasks), "matching_tasks": len(same), "scope": "read from the CRM app's API, independent of the browser toast"}
            if len(same) > 1:
                return "FAILED", {**ev, "reason": "duplicate_tasks_detected"}
            if not mine:
                return "FAILED", {**ev, "reason": "no_task_at_crm (the UI may have reported success without writing)"}
            return "VERIFIED", {**ev, "provider_ref": mine[0]["id"]}
        msgs = rb.get_json(self.world.outbox.url + "/api/messages")
        same = [m for m in msgs if m["to_addr"] == params["to_addr"] and m["attachment_sha256"] == params["attachment_sha256"]]
        mine = [m for m in same if m.get("op_id") == idempotency_key]
        ev = {"messages_before": snapshot.get("messages_before"), "messages_now": len(msgs), "matching_messages": len(same), "delivery": "SIMULATED: nothing left this machine",
              "scope": "read from the outbox app's API, independent of the browser toast"}
        if len(same) > 1:
            return "FAILED", {**ev, "reason": "duplicate_messages_detected"}
        if not mine:
            return "FAILED", {**ev, "reason": "no_message_at_outbox"}
        return "VERIFIED", {**ev, "provider_ref": mine[0]["id"], "attachment_sha256": mine[0]["attachment_sha256"]}
