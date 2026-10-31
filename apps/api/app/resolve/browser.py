"""Cloud-browser executor (inherited RESOLVE design, rebuilt for REDEEM's multi-tenant engine).

What is real: a real Chromium (Playwright) drives real DOM forms in apps served on loopback by this process; every action takes before/after
snapshots (URL, title, DOM-text hash, ARIA hash, screenshot hash, API hash = 'state fusion'); a request allow-list aborts any non-fixture origin; a
temporal guard re-reads the target immediately before acting; pages that need a login / CAPTCHA / MFA / payment pause the mission for the user.
What is NOT claimed: strong tenant isolation. Each run uses a fresh browser context in a separate browser process, but on the same host, and it may only
visit the tenant's own loopback fixture world. Browsing arbitrary external sites stays BLOCKED (see policy.ssrf.browser_execution_allowed)."""
import hashlib
import json
import os
import shutil
import threading
import urllib.request
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..config import settings
from ..db import utcnow
from ..models import BrowserSessionRow, BrowserSnapshot
from .web_fixtures import FixtureWorld

CURRENT: ContextVar[dict | None] = ContextVar("current_action", default=None)   # set by the engine around each dispatch
_worlds: dict[str, FixtureWorld] = {}
_lock = threading.Lock()


def chromium_path() -> str | None:
    p = os.environ.get("REDEEM_CHROMIUM") or settings.chromium_path
    if p and Path(p).exists():
        return p
    return "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None


def browser_available() -> tuple[bool, str]:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "playwright is not installed"
    if chromium_path() or os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return True, "ok"
    # `python -m playwright install chromium` puts its managed build in the default cache; Playwright launches it without an explicit path.
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"
    if any(cache.glob("chromium*")):
        return True, "ok (playwright-managed chromium)"
    return False, "no Chromium binary found (set REDEEM_CHROMIUM)"


def world_for(tenant_id: str) -> FixtureWorld:
    with _lock:
        w = _worlds.get(tenant_id)
        if not w:
            w = _worlds[tenant_id] = FixtureWorld(Path(settings.data_dir) / "browser" / tenant_id / "world", settings.allow_fault_injection, seed=0)
        return w


def reset_world(tenant_id: str) -> FixtureWorld:
    with _lock:
        w = _worlds.pop(tenant_id, None)
        if w:
            w.stop()
        shutil.rmtree(Path(settings.data_dir) / "browser" / tenant_id / "world", ignore_errors=True)
    return world_for(tenant_id)


def drop_world(tenant_id: str) -> None:
    with _lock:
        w = _worlds.pop(tenant_id, None)
        if w:
            w.stop()
    shutil.rmtree(Path(settings.data_dir) / "browser" / tenant_id, ignore_errors=True)


def shutdown_all() -> None:
    with _lock:
        for w in _worlds.values():
            w.stop()
        _worlds.clear()


def get_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # loopback fixture apps only
        return json.loads(r.read())


def set_fault(world: FixtureWorld, app: str, name: str, value=True) -> None:
    getattr(world, app).faults[name] = value


class UserActionRequired(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


class RunStopped(Exception):
    """The user pressed Stop on a live run."""


class StaleState(Exception):
    pass


_USER_ONLY = [("login", "input[type=password]"), ("captcha", "iframe[src*=captcha], [id*=captcha i], [class*=captcha i], text=/verify you are (a )?human/i"),
              ("mfa", "text=/one[- ]time (password|code)|\\bOTP\\b|verification code/i"), ("payment", "input[autocomplete=cc-number], text=/enter (your )?card number|confirm payment/i")]


class BrowserRun:
    def __init__(self, db: Session, tenant_id: str, world: FixtureWorld, mission_id: str | None = None, action_id: str | None = None):
        self.db, self.tenant_id, self.world, self.mission_id, self.action_id = db, tenant_id, world, mission_id, action_id
        self.origins = [world.crm.url, world.docs.url, world.outbox.url]
        self.blocked: list[str] = []
        self.snaps: list[dict] = []
        self.row: BrowserSessionRow | None = None
        self.fallbacks: list[str] = []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.row = BrowserSessionRow(tenant_id=self.tenant_id, mission_id=self.mission_id, action_id=self.action_id, origins=self.origins)
        self.db.add(self.row)
        self.db.commit()
        self._pw = sync_playwright().start()
        opts = {"headless": True, "args": ["--no-sandbox"]}
        if chromium_path():
            opts["executable_path"] = chromium_path()
        self._browser = self._pw.chromium.launch(**opts)
        self.ctx = self._browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False, service_workers="block")
        self.ctx.route("**/*", self._route)
        return self

    def _route(self, route):
        u = route.request.url
        if any(u.startswith(o) for o in self.origins) or u.startswith(("data:", "about:")):
            return route.continue_()
        self.blocked.append(u[:200])
        return route.abort()

    def page(self):
        p = self.ctx.new_page()
        p.set_default_timeout(8000)
        return p

    def guard_user_only(self, page) -> None:
        """Pause for steps only the user may do. REDEEM never types a password, solves a CAPTCHA, reads an OTP or confirms a payment."""
        for reason, sel in _USER_ONLY:
            try:
                if page.locator(sel).count():
                    raise UserActionRequired(reason, page.url)
            except UserActionRequired:
                raise
            except Exception:
                continue

    def dismiss_popups(self, page) -> bool:
        b = page.get_by_role("button", name="Dismiss")
        if b.count():
            b.click()
            self.fallbacks.append("dismissed an unexpected modal instead of clicking through it")
            return True
        return False

    def snapshot(self, page, phase: str, label: str, api_state=None) -> dict:
        txt = page.locator("body").inner_text()
        try:
            aria = page.locator("body").aria_snapshot()
        except Exception:
            aria = ""
        d = Path(settings.data_dir) / "browser" / self.tenant_id / "shots"
        d.mkdir(parents=True, exist_ok=True)
        sid = f"snp_{hashlib.sha256((self.row.id + label + phase + str(len(self.snaps))).encode()).hexdigest()[:12]}"
        path = d / f"{sid}.png"
        page.screenshot(path=str(path))
        shot = hashlib.sha256(path.read_bytes()).hexdigest()
        h = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731
        fused = {"url": page.url, "title": page.title(), "dom_sha": h(txt), "aria_sha": h(aria), "screenshot_sha": shot, "api_sha": h(json.dumps(api_state, sort_keys=True)) if api_state is not None else None,
                 "elements": page.locator("*").count()}
        row = BrowserSnapshot(id=sid, tenant_id=self.tenant_id, session_id=self.row.id, mission_id=self.mission_id, action_id=self.action_id, phase=phase, label=label, url=page.url,
                              title=fused["title"][:190], dom_sha=fused["dom_sha"], aria_sha=fused["aria_sha"], screenshot_path=str(path), screenshot_sha=shot, fused=fused)
        self.db.add(row)
        self.db.commit()
        self.snaps.append({"id": sid, "phase": phase, "label": label, **fused})
        return self.snaps[-1]

    def fill_first(self, page, labels: list[str], value: str) -> str:
        """Semantic locators with fallbacks: survives a renamed label (RESOLVE's layout-shift fault). Records which fallback was used."""
        for i, lab in enumerate(labels):
            loc = page.get_by_label(lab)
            if loc.count():
                loc.fill(value)
                if i:
                    self.fallbacks.append(f"label '{labels[0]}' not found; used '{lab}'")
                return lab
        raise StaleState(f"no field matching any of {labels}")

    def click_first(self, page, names: list[str]) -> str:
        for i, n in enumerate(names):
            loc = page.get_by_role("button", name=n)
            if loc.count():
                loc.click()
                if i:
                    self.fallbacks.append(f"button '{names[0]}' not found; used '{n}'")
                return n
        raise StaleState(f"no button matching any of {names}")

    def __exit__(self, et, ev, tb):
        status = "DONE"
        ua = None
        if et is UserActionRequired:
            status, ua = "USER_ACTION_REQUIRED", {"reason": ev.reason, "detail": ev.detail}
        elif et is RunStopped:
            status = "STOPPED"
        elif et is not None:
            status = "FAILED"
        try:
            self.row.status, self.row.ended_at, self.row.blocked_requests, self.row.user_action = status, utcnow(), self.blocked, ua
            self.row.note = "; ".join(self.fallbacks)[:500] or None
            self.db.commit()
        finally:
            for c in (self.ctx, self._browser):
                try:
                    c.close()
                except Exception:
                    pass
            self._pw.stop()
        return False


def observe_world(db: Session, tenant_id: str, mission_id: str | None = None) -> dict:
    """Observer: read the CRM and report store THROUGH THE BROWSER DOM (like RESOLVE), with snapshots. Returns contacts and reports."""
    w = world_for(tenant_id)
    with BrowserRun(db, tenant_id, w, mission_id, None) as br:
        page = br.page()
        page.goto(w.crm.url)
        br.guard_user_only(page)
        br.dismiss_popups(page)
        page.get_by_test_id("contact-row").first.wait_for(timeout=10000)
        contacts = []
        for r in page.get_by_test_id("contact-row").all():
            c = r.locator("td").all_inner_texts()
            contacts.append({"id": r.get_attribute("data-contact-id"), "name": c[1], "email": c[2], "org": c[3], "dept": c[4]})
        br.snapshot(page, "observe", "crm contacts", contacts)
        page.goto(w.docs.url)
        page.get_by_test_id("report-row").first.wait_for(timeout=10000)
        reports = []
        for r in page.get_by_test_id("report-row").all():
            c = r.locator("td").all_inner_texts()
            reports.append({"id": r.get_attribute("data-report-id"), "title": c[1], "version": c[2], "contact_id": c[3], "modified_at": r.get_attribute("data-modified"), "sha256": r.get_attribute("data-sha256")})
        br.snapshot(page, "observe", "report store", reports)
    return {"contacts": contacts, "reports": reports, "snapshots": br.snaps, "fallbacks": br.fallbacks}


def report_bytes_sha(world: FixtureWorld, report_id: str) -> str | None:
    """Corroborate a report's registry hash against the bytes actually served (like RESOLVE's disk corroboration)."""
    try:
        with urllib.request.urlopen(f"{world.docs.url}/files/{report_id}", timeout=5) as r:
            return hashlib.sha256(r.read()).hexdigest()
    except Exception:
        return None


def host_of(url: str) -> str:
    return urlparse(url).netloc
