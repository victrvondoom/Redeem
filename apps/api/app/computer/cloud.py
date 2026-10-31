"""Cloud computer: a separate X display (Xvfb) with a real Chromium window and its own REDEEM bridge process.

Each cloud computer has its own display number, browser profile directory and device credentials, and everything is
deleted when the session ends. Isolation is process-level inside the API host; it is NOT a VM or container sandbox
(see docs/REDEEM_REAL_COMPUTER_EXECUTION_REPORT.md)."""
from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from ..core.security import hash_token
from ..models import ComputerDevice
from . import hub

BRIDGE_DIR = Path(__file__).resolve().parents[3] / "bridge"
_running: dict[str, dict] = {}
_lock = threading.Lock()


def available() -> tuple[bool, str]:
    if sys.platform != "linux":
        return False, "cloud computers need a Linux host with Xvfb"
    if not shutil.which("Xvfb"):
        return False, "Xvfb is not installed on the server"
    if not (BRIDGE_DIR / "redeem_bridge").is_dir():
        return False, "bridge package not found"
    try:
        import mss  # noqa: F401
        import Xlib  # noqa: F401
    except ImportError:
        return False, "bridge dependencies (mss, python-xlib) are not installed on the server"
    return True, "ok"


def _free_display() -> int:
    for n in range(120, 220):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists():
            return n
    raise RuntimeError("no free display")


def start(db, tenant_id: str, user_id: str, server_url: str, width: int = 1280, height: int = 800) -> ComputerDevice:
    ok, why = available()
    if not ok:
        raise RuntimeError(why)
    n = _free_display()
    work = Path(tempfile.mkdtemp(prefix="redeem-cloud-"))
    xvfb = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if Path(f"/tmp/.X11-unix/X{n}").exists():
            break
        time.sleep(0.1)
    token = secrets.token_urlsafe(32)
    dev = ComputerDevice(tenant_id=tenant_id, user_id=user_id, name=f"Cloud computer :{n}", kind="cloud", platform="x11", token_hash=hash_token(token))
    db.add(dev)
    db.commit()
    cfg = work / "bridge.json"
    import json
    cfg.write_text(json.dumps({"server": server_url.rstrip("/"), "device_id": dev.id, "token": token}))
    os.chmod(cfg, 0o600)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("REDEEM_", "BOLNA_", "GOOGLE_"))}  # no server secrets in the desktop
    env.update(DISPLAY=f":{n}", REDEEM_BRIDGE_CONFIG=str(cfg), REDEEM_BRIDGE_PROFILE=str(work / "browser"), PYTHONPATH=str(BRIDGE_DIR), HOME=str(work))
    bridge = subprocess.Popen([sys.executable, "-m", "redeem_bridge", "run", "--no-ui"], cwd=str(work), env=env, stdout=open(work / "bridge.log", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    with _lock:
        _running[dev.id] = {"xvfb": xvfb, "bridge": bridge, "dir": work, "display": n}
    for _ in range(100):
        if hub.online(dev.id):
            break
        if bridge.poll() is not None:
            break
        time.sleep(0.15)
    if not hub.online(dev.id):
        log = (work / "bridge.log").read_text()[-400:] if (work / "bridge.log").exists() else ""
        stop(dev.id)
        dev.status = "REVOKED"
        db.commit()
        raise RuntimeError(f"cloud bridge did not connect: {log}")
    return dev


def stop(device_id: str) -> None:
    with _lock:
        r = _running.pop(device_id, None)
    if not r:
        return
    for p in (r["bridge"], r["xvfb"]):
        try:
            os.killpg(p.pid, signal.SIGTERM)  # the bridge's browser shares its process group
        except Exception:
            pass
    for p in (r["bridge"], r["xvfb"]):
        try:
            p.wait(5)
        except Exception:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                pass
    shutil.rmtree(r["dir"], ignore_errors=True)


def stop_all() -> None:
    for d in list(_running):
        stop(d)
