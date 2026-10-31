"""Registry of connected bridges. Bridges connect *out* to this server over an authenticated WebSocket; the server
never opens a connection to a user's computer. Calls are request/response with ids and a hard timeout."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from ..config import settings
from ..core.security import hash_token
from ..db import SessionLocal, utcnow
from ..models import ComputerDevice, ComputerFrame, ComputerSession


class DeviceOffline(RuntimeError):
    pass


@dataclass
class Conn:
    device_id: str
    tenant_id: str
    ws: WebSocket
    loop: asyncio.AbstractEventLoop
    pending: dict = field(default_factory=dict)
    state: str = "active"
    platform: str = ""


_conns: dict[str, Conn] = {}
_lock = threading.Lock()
_frame_listeners: list = []


def online(device_id: str) -> bool:
    return device_id in _conns


def device_state(device_id: str) -> str | None:
    c = _conns.get(device_id)
    return c.state if c else None


def store_frame(db, tenant_id: str, session_id: str, obs: dict) -> ComputerFrame:
    png = base64.b64decode(obs["png_b64"])
    if hashlib.sha256(png).hexdigest() != obs.get("sha256"):
        raise ValueError("frame hash mismatch")
    d = Path(settings.data_dir) / "computer" / tenant_id / session_id
    d.mkdir(parents=True, exist_ok=True)
    f = ComputerFrame(tenant_id=tenant_id, session_id=session_id, frame_no=int(obs.get("frame_no", 0)), monitor=int(obs.get("monitor", 0)),
                      origin_x=int(obs.get("origin_x", 0)), origin_y=int(obs.get("origin_y", 0)), width=int(obs["width"]), height=int(obs["height"]),
                      sha256=obs["sha256"], path="", active_window=obs.get("active_window"), cursor=obs.get("cursor"))
    db.add(f)
    db.flush()
    p = d / f"{f.id}.png"
    p.write_bytes(png)
    f.path = str(p)
    s = db.get(ComputerSession, session_id)
    if s:
        s.latest_frame_id = f.id
    return f


def _active_session(db, device_id: str) -> ComputerSession | None:
    return db.scalar(select(ComputerSession).where(ComputerSession.device_id == device_id, ComputerSession.status.in_(["ACTIVE", "PAUSED", "USER_CONTROL"]))
                     .order_by(ComputerSession.created_at.desc()))


async def serve(ws: WebSocket) -> None:
    await ws.accept()
    try:
        hello = json.loads(await asyncio.wait_for(ws.receive_text(), 15))
    except Exception:
        await ws.close(code=4400)
        return
    with SessionLocal() as db:
        dev = db.scalar(select(ComputerDevice).where(ComputerDevice.id == str(hello.get("device_id", ""))[:40]))
        if not dev or dev.status != "PAIRED" or not secrets.compare_digest(dev.token_hash, hash_token(str(hello.get("token", ""))[:200])):
            await ws.send_text(json.dumps({"type": "error", "error": "invalid_device_credentials"}))
            await ws.close(code=4401)
            return
        new = secrets.token_urlsafe(32)  # rotate on every connection
        dev.token_hash, dev.token_rotated_at, dev.last_seen_at = hash_token(new), utcnow(), utcnow()
        dev.platform = str(hello.get("platform", ""))[:20]
        dev.monitors = hello.get("monitors") if isinstance(hello.get("monitors"), list) else []
        db.commit()
        conn = Conn(dev.id, dev.tenant_id, ws, asyncio.get_running_loop(), platform=dev.platform)
    with _lock:
        old = _conns.get(conn.device_id)
        _conns[conn.device_id] = conn
    if old:
        try:
            await old.ws.close(code=4409)
        except Exception:
            pass
    await ws.send_text(json.dumps({"type": "welcome", "token": new}))
    try:
        while True:
            m = json.loads(await ws.receive_text())
            t = m.get("type")
            if t == "result" and m.get("id") in conn.pending:
                conn.state = m.get("state", conn.state)
                conn.pending.pop(m["id"]).set_result(m)
            elif t == "frame":
                conn.state = m.get("state", conn.state)
                with SessionLocal() as db:
                    s = _active_session(db, conn.device_id)
                    if s and s.status != "ENDED":
                        try:
                            store_frame(db, conn.tenant_id, s.id, m["observation"])
                            db.commit()
                        except Exception:
                            db.rollback()
            elif t == "local_control":
                op = m.get("op")
                conn.state = {"stop": "stopped", "pause": "paused", "request_takeover": "user_has_control", "resume": "active"}.get(op, conn.state)
                with SessionLocal() as db:  # the person at the computer outranks the server
                    s = _active_session(db, conn.device_id)
                    if s:
                        s.status = {"stop": "STOPPED", "pause": "PAUSED", "request_takeover": "USER_CONTROL", "resume": "ACTIVE"}.get(op, s.status)
                        s.control_epoch += 1
                        db.commit()
    except (WebSocketDisconnect, RuntimeError, json.JSONDecodeError):
        pass
    finally:
        with _lock:
            if _conns.get(conn.device_id) is conn:
                del _conns[conn.device_id]
        for f in conn.pending.values():
            if not f.done():
                f.set_exception(DeviceOffline("bridge disconnected before answering"))


async def _call(conn: Conn, msg: dict, timeout: float) -> dict:
    fut = conn.loop.create_future()
    conn.pending[msg["id"]] = fut
    await conn.ws.send_text(json.dumps(msg))
    try:
        return await asyncio.wait_for(fut, timeout)
    finally:
        conn.pending.pop(msg["id"], None)


def call(device_id: str, action: str, params: dict, label: str = "", timeout: float = 30.0, actor: str = "agent") -> dict:
    """Blocking call from worker threads. Raises DeviceOffline or TimeoutError; a timeout means the outcome is UNKNOWN."""
    conn = _conns.get(device_id)
    if not conn:
        raise DeviceOffline("the computer is not connected")
    msg = {"type": "cmd", "id": secrets.token_hex(8), "action": action, "params": params, "label": label, "actor": actor}
    fut = asyncio.run_coroutine_threadsafe(_call(conn, msg, timeout), conn.loop)
    return fut.result(timeout + 2)


def kick(device_id: str, reason: str = "revoked") -> None:
    conn = _conns.get(device_id)
    if not conn:
        return

    async def go():
        try:
            await conn.ws.send_text(json.dumps({"type": reason}))
            await conn.ws.close(code=4401)
        except Exception:
            pass
    asyncio.run_coroutine_threadsafe(go(), conn.loop)
