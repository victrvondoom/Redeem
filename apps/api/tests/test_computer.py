"""Computer use against REAL displays: an Xvfb X server, a real Chromium window, the real REDEEM bridge process
injecting input through XTEST, and a live uvicorn server. Nothing here is mocked; tests skip if Xvfb is missing."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from app.computer import cloud
from app.computer import protocol as P
from app.config import settings
from app.main import app

BRIDGE = Path(__file__).resolve().parents[2] / "bridge"
needs_x = pytest.mark.skipif(not cloud.available()[0], reason="needs Xvfb and the bridge dependencies")
CRM = ("Open the CRM on my computer. Find Priya Sharma, update her preferred contact method to WhatsApp, "
       "create a follow-up for tomorrow at 10 AM, and prepare a message draft. Do not send it.")


@pytest.fixture(scope="module")
def server():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    os.environ["REDEEM_PUBLIC_API_URL"] = f"http://127.0.0.1:{port}"
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    cloud.stop_all()
    srv.should_exit = True


class Live:
    def __init__(self, base, email):
        self.c = httpx.Client(base_url=base, timeout=90)
        r = self.c.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery", "name": "Asha"})
        assert r.status_code == 201, r.text
        self.me = r.json()
        self.h = {"X-CSRF-Token": self.me["csrf_token"]}

    def get(self, u):
        return self.c.get(u)

    def post(self, u, j=None):
        return self.c.post(u, json=j, headers=self.h)

    def delete(self, u):
        return self.c.delete(u, headers=self.h)

    def task(self, tid):
        return self.get(f"/api/v1/computer/tasks/{tid}").json()

    def wait(self, tid, until=lambda t: t["status"] not in ("PLANNING", "RUNNING"), timeout=150):
        end = time.time() + timeout
        while time.time() < end:
            t = self.task(tid)
            if until(t):
                return t
            time.sleep(0.3)
        raise AssertionError(f"timeout; last: {t['status']} {t['step']}")


@pytest.fixture
def live(server):
    yield Live(server, f"u{time.time_ns()}@example.com")
    cloud.stop_all()


def _cloud(live):
    r = live.post("/api/v1/computer/cloud")
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- protocol
def test_protocol_mirror_is_identical_and_validates():
    a = (BRIDGE / "redeem_bridge" / "protocol.py").read_text()
    b = Path(P.__file__).read_text().split("\n", 1)[1]
    assert a == b
    for action, params in [("key_combination", {"combo": "ctrl+alt+delete"}), ("key_combination", {"combo": "win+r"}), ("launch_application", {"app": "C:/evil.exe"}),
                           ("open_url", {"url": "file:///etc/passwd"}), ("type_text", {"text": "a\x1bb"}), ("click_coordinates", {"x": "1", "y": 2}), ("shell", {})]:
        with pytest.raises(P.InvalidAction):
            P.validate(action, params)
    assert P.validate("key_combination", {"combo": "Ctrl+S"}) == {"combo": "ctrl+s"}


# ---------------------------------------------------------------- my computer: pairing a real bridge process
@needs_x
def test_pair_rotate_isolate_and_revoke_a_real_bridge(live, server, tmp_path):
    other = Live(server, f"o{time.time_ns()}@example.com")
    code = live.post("/api/v1/computer/pairing-codes").json()["code"]
    disp = 230 + os.getpid() % 20
    xvfb = subprocess.Popen(["Xvfb", f":{disp}", "-screen", "0", "1024x700x24", "-nolisten", "tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = {**os.environ, "DISPLAY": f":{disp}", "PYTHONPATH": str(BRIDGE), "REDEEM_BRIDGE_CONFIG": str(tmp_path / "b.json"), "HOME": str(tmp_path)}
    try:
        time.sleep(0.8)
        out = subprocess.run([sys.executable, "-m", "redeem_bridge", "pair", "--server", server, "--code", code, "--name", "Test PC"], env=env, capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        again = subprocess.run([sys.executable, "-m", "redeem_bridge", "pair", "--server", server, "--code", code], env=env, capture_output=True, text=True, timeout=30)
        assert again.returncode != 0  # one-time code
        first_token = json.loads((tmp_path / "b.json").read_text())["token"]
        proc = subprocess.Popen([sys.executable, "-m", "redeem_bridge", "run", "--no-ui"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        dev = None
        for _ in range(60):
            items = live.get("/api/v1/computer/devices").json()["items"]
            if items and items[0]["online"]:
                dev = items[0]
                break
            time.sleep(0.25)
        assert dev and dev["name"] == "Test PC" and dev["platform"] == "x11" and dev["monitors"][0]["width"] == 1024
        assert json.loads((tmp_path / "b.json").read_text())["token"] != first_token  # rotated on connect
        # tenant isolation
        assert other.get("/api/v1/computer/devices").json()["items"] == []
        assert other.post("/api/v1/computer/sessions", {"device_id": dev["id"]}).status_code == 404
        assert other.delete(f"/api/v1/computer/devices/{dev['id']}").status_code == 404
        s = live.post("/api/v1/computer/sessions", {"device_id": dev["id"]}).json()
        assert s["frame"] and s["frame"]["width"] == 1024
        png = live.get(s["frame"]["url"])
        assert png.content[:4] == b"\x89PNG" and other.get(s["frame"]["url"]).status_code == 404
        assert other.get(f"/api/v1/computer/sessions/{s['session']['id']}/live").status_code == 404
        # revoke: the bridge is told, deletes its credentials and exits
        assert live.delete(f"/api/v1/computer/devices/{dev['id']}").status_code == 204
        proc.wait(20)
        assert not (tmp_path / "b.json").exists()
        assert live.get("/api/v1/computer/devices").json()["items"] == []
    finally:
        xvfb.terminate()


def test_expired_and_unknown_codes_are_refused(live, db):
    from datetime import timedelta

    from app.core.security import hash_token
    from app.db import utcnow
    from app.models import PairingCode
    db.add(PairingCode(code_hash=hash_token("ABCD-EFGH"), tenant_id="t", user_id="u", expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    for code in ("ABCD-EFGH", "ZZZZ-ZZZZ"):
        assert live.post("/api/v1/computer/pair/claim", {"code": code}).status_code == 400


# ---------------------------------------------------------------- the CRM operator, end to end through the UI
@needs_x
def test_crm_scenario_through_real_mouse_and_keyboard(live):
    s = _cloud(live)
    sid = s["session"]["id"]
    t = live.post(f"/api/v1/computer/sessions/{sid}/tasks", {"instruction": CRM}).json()
    t = live.wait(t["id"])
    assert t["status"] == "DONE", t["report"]
    st = t["report"]["stored_state"]
    assert st["preferred_contact"] == "WhatsApp" and st["followups"][0]["time"] == "10:00" and st["drafts"] == 1 and st["sent"] == 0
    assert "NOT sent" in t["report"]["summary"]
    assert all(c["observed"] for c in t["report"]["after_reload"])
    kinds = {a["action"] for a in t["actions"]}
    assert kinds <= {"observe_screen", "open_url", "click_element", "type_text", "key_combination"}  # the CRM was changed only through the UI
    clicks = [a for a in t["actions"] if a["action"] == "click_element"]
    assert all(a["target"]["frame_id"] and a["target"]["bbox"] and a["after_frame_id"] for a in clicks)
    assert not any(a["target"]["label"] == "Send message" for a in clicks)


@needs_x
def test_pause_takeover_user_changes_page_then_agent_replans(live):
    s = _cloud(live)
    sid = s["session"]["id"]
    t = live.post(f"/api/v1/computer/sessions/{sid}/tasks", {"instruction": CRM}).json()
    live.wait(t["id"], until=lambda x: any(e["step"].startswith("verified: Current preferred contact") for e in (x["report"] or {}).get("log", [])))
    assert live.post(f"/api/v1/computer/sessions/{sid}/control", {"op": "pause"}).json()["status"] == "PAUSED"
    live.wait(t["id"], until=lambda x: x["status"] == "PAUSED", timeout=30)
    n = len([a for a in live.task(t["id"])["actions"] if a["actor"] == "agent" and a["action"] != "observe_screen" and a["status"] == "DONE"])
    time.sleep(2)
    assert len([a for a in live.task(t["id"])["actions"] if a["actor"] == "agent" and a["action"] != "observe_screen" and a["status"] == "DONE"]) == n
    # the person takes over and drives the same computer: they go back to the customer list
    assert live.post(f"/api/v1/computer/sessions/{sid}/input", {"action": "click_coordinates", "params": {"x": 70, "y": 216}}).status_code == 409  # paused, not in control
    live.post(f"/api/v1/computer/sessions/{sid}/control", {"op": "takeover"})
    r = live.post(f"/api/v1/computer/sessions/{sid}/input", {"action": "click_coordinates", "params": {"x": 70, "y": 216}})  # "All customers"
    assert r.status_code == 200 and r.json()["ok"]
    live.post(f"/api/v1/computer/sessions/{sid}/control", {"op": "release"})
    t = live.wait(t["id"], until=lambda x: x["status"] not in ("PLANNING", "RUNNING", "PAUSED", "USER_CONTROL"))
    assert t["status"] == "DONE", t["report"]
    steps = [e["step"] for e in t["report"]["log"]]
    assert "control returned: observing the current screen again" in steps
    acts = live.get(f"/api/v1/computer/sessions/{sid}/live").json()["actions"]
    assert any(a["actor"] == "user" and a["status"] == "DONE" for a in acts)


@needs_x
def test_emergency_stop_interrupts_typing(live):
    s = _cloud(live)
    sid = s["session"]["id"]
    t = live.post(f"/api/v1/computer/sessions/{sid}/tasks", {"instruction": "type " + "stop me " * 120}).json()
    live.wait(t["id"], until=lambda x: any(a["action"] == "type_text" for a in x["actions"]), timeout=30)
    time.sleep(0.4)
    assert live.post(f"/api/v1/computer/sessions/{sid}/control", {"op": "stop"}).json()["status"] == "STOPPED"
    t = live.wait(t["id"], timeout=30)
    typing = [a for a in t["actions"] if a["action"] == "type_text"][0]
    assert t["status"] in ("STOPPED", "FAILED") and typing["status"] in ("BLOCKED", "FAILED") and "stopped" in (typing["error"] or "")
    assert live.post(f"/api/v1/computer/sessions/{sid}/tasks", {"instruction": "type hello"}).status_code == 409


@needs_x
def test_sending_needs_an_approval_bound_to_the_exact_action(live):
    s = _cloud(live)
    sid = s["session"]["id"]
    t = live.post(f"/api/v1/computer/sessions/{sid}/tasks", {"instruction": "Open the CRM, find Priya Sharma, prepare a message draft and send it."}).json()
    t = live.wait(t["id"])
    assert t["status"] == "NEEDS_APPROVAL" and t["pending_approval"]["target"]["label"] == "Send message"
    assert live.post(f"/api/v1/computer/tasks/{t['id']}/approve", {"digest": "0" * 64}).status_code == 409
    r = live.post(f"/api/v1/computer/tasks/{t['id']}/approve", {"digest": t["pending_approval"]["digest"]})
    assert r.status_code == 200
    t = live.wait(t["id"])
    assert t["status"] == "DONE" and t["report"]["stored_state"]["sent"] == 1, t["report"]


def test_stale_target_detection(db, tmp_path):
    from PIL import Image

    from app.computer.pipeline import _target_moved
    from app.models import ComputerFrame

    def frame(color, title="CRM"):
        p = tmp_path / f"{time.time_ns()}.png"
        im = Image.new("RGB", (200, 100), "white")
        im.paste(color, (50, 40, 110, 60))
        im.save(p)
        f = ComputerFrame(tenant_id="t", session_id="s", frame_no=1, width=200, height=100, sha256="x", path=str(p), active_window={"title": title})
        db.add(f)
        db.commit()
        return f
    a, same, moved, other = frame("black"), frame("black"), frame("white"), frame("black", "Other window")
    tgt = {"frame_id": a.id, "bbox": {"x": 50, "y": 40, "w": 60, "h": 20}}
    assert not _target_moved(db, tgt, same.id)
    assert _target_moved(db, tgt, moved.id)
    assert _target_moved(db, tgt, other.id)


# ---------------------------------------------------------------- Bolna voice control plane
@needs_x
def test_bolna_tools_drive_the_computer(live, db):
    from app.models import Call
    settings.bolna_webhook_secret = "whsec_test"
    s = _cloud(live)
    call = Call(tenant_id=live.me["tenant_id"], user_id=live.me["id"], provider="bolna", execution_id="exec-123", kind="web", status="in-progress")
    db.add(call)
    db.commit()
    tool = lambda name, **a: live.c.post(f"/api/v1/voice/tools/{name}?token=whsec_test", json={"execution_id": "exec-123", **a})  # noqa: E731
    assert live.c.post("/api/v1/voice/tools/computer_status?token=wrong", json={"execution_id": "exec-123"}).status_code == 401
    r = tool("computer_task", instruction="what's on my screen")
    assert r.status_code == 200 and r.json()["ok"], r.text
    t = live.wait(r.json()["task_id"])
    assert t["source"] == "voice" and t["call_id"] == call.id and t["status"] == "DONE"
    st = tool("computer_status").json()
    assert st["status"] == "DONE" and "Active window" in st["say"]
    assert tool("computer_control", op="pause").json()["status"] == "PAUSED"
    assert tool("computer_control", op="continue").json()["status"] == "ACTIVE"
    assert live.get(f"/api/v1/computer/sessions/{s['session']['id']}/live").json()["session"]["status"] == "ACTIVE"
