"""Pairing and the outbound WebSocket session. The bridge never listens on a port."""
from __future__ import annotations

import json
import os
import platform as pyplatform
import stat
import threading
import time
import urllib.request
from pathlib import Path

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from . import __version__
from .executor import Executor

CONFIG = Path(os.environ.get("REDEEM_BRIDGE_CONFIG") or Path.home() / ".redeem-bridge.json")


def _save(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg))
    try:
        os.chmod(CONFIG, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def load() -> dict | None:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else None


def pair(server: str, code: str, name: str | None = None, plat=None) -> dict:
    body = {"code": code.strip().upper(), "name": name or pyplatform.node()[:60] or "computer", "platform": (plat.name if plat else pyplatform.system().lower()),
            "os_version": pyplatform.platform()[:80], "bridge_version": __version__}
    req = urllib.request.Request(server.rstrip("/") + "/api/v1/computer/pair/claim", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read())
    cfg = {"server": server.rstrip("/"), "device_id": out["device_id"], "token": out["device_token"]}
    _save(cfg)
    return cfg


class Bridge:
    def __init__(self, cfg: dict, plat, on_status=lambda s: None, stream_interval: float = 1.0):
        self.cfg, self.ex, self.on_status = cfg, Executor(plat), on_status
        self.stream = threading.Event()
        self.stream_interval = stream_interval
        self.quit = threading.Event()
        self.revoked = False
        self.ws = None
        self.send_lock = threading.Lock()
        self.on_target = lambda x, y, label: None  # the pointer overlay hooks in here

    def _url(self):
        s = self.cfg["server"]
        return ("wss://" + s[8:] if s.startswith("https://") else "ws://" + s[7:]) + "/api/v1/computer/bridge/ws"

    def send(self, msg: dict):
        with self.send_lock:
            if self.ws:
                self.ws.send(json.dumps(msg))

    def _streamer(self):
        while not self.quit.is_set():
            if self.stream.is_set() and self.ws and not self.ex.stopped.is_set():
                try:
                    self.send({"type": "frame", "observation": self.ex.observe(), "state": self.ex.blocked() or "active"})
                except Exception:
                    pass
            time.sleep(self.stream_interval)

    def _handle(self, m: dict):
        if m.get("type") == "cmd":
            a = m.get("action", "")
            if a == "start_recording":
                self.stream.set()
                res = {"ok": True}
            elif a == "stop_recording":
                self.stream.clear()
                res = {"ok": True}
            else:
                prm = m.get("params") or {}
                if isinstance(prm.get("x"), int) and isinstance(prm.get("y"), int):
                    self.on_target(prm["x"], prm["y"], str(m.get("label") or a)[:40])
                res = self.ex.run(a, prm, actor="user" if m.get("actor") == "user" else "agent")
            self.send({"type": "result", "id": m.get("id"), **res, "state": self.ex.blocked() or "active"})
            self.on_status(f"{a}: {'ok' if res.get('ok') else res.get('error')}")

    def local(self, op: str):
        """Called from the bridge window or Ctrl+C: always applied, then reported to the server."""
        self.ex.run(op, {})
        try:
            self.send({"type": "local_control", "op": op})
        except Exception:
            pass

    def run_forever(self):
        threading.Thread(target=self._streamer, daemon=True).start()
        backoff = 1
        while not self.quit.is_set() and not self.revoked:
            try:
                with connect(self._url(), open_timeout=15, max_size=8 * 1024 * 1024) as ws:
                    ws.send(json.dumps({"type": "hello", "device_id": self.cfg["device_id"], "token": self.cfg["token"], "version": __version__,
                                        "platform": self.ex.p.name, "monitors": [m.__dict__ for m in self.ex.p.monitors()]}))
                    w = json.loads(ws.recv(timeout=15))
                    if w.get("type") != "welcome":
                        raise PermissionError(w.get("error", "rejected"))
                    self.cfg["token"] = w["token"]  # rotated on every connection; the old token is now dead
                    _save(self.cfg)
                    self.ws, backoff = ws, 1
                    self.on_status("connected")
                    for raw in ws:
                        m = json.loads(raw)
                        if m.get("type") == "revoked":
                            self.revoked = True
                            break
                        threading.Thread(target=self._handle, args=(m,), daemon=True).start() if m.get("action") not in ("stop", "pause", "request_takeover") else self._handle(m)
            except PermissionError as e:
                self.on_status(f"rejected: {e}")
                self.revoked = True
            except (OSError, ConnectionClosed, TimeoutError) as e:
                self.on_status(f"disconnected ({type(e).__name__}); retrying in {backoff}s")
            finally:
                self.ws = None
            if self.revoked:
                break
            self.quit.wait(backoff)
            backoff = min(backoff * 2, 30)
        if self.revoked and CONFIG.exists():
            CONFIG.unlink()
            self.on_status("access revoked: credentials deleted")
