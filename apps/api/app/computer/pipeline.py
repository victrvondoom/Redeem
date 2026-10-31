"""Every computer action, from the agent or from the person, passes through this pipeline:

identity -> device session -> schema -> permission -> risk/approval -> stale-state -> persist -> native execution
-> new observation -> evidence. A dispatch whose outcome is unknown is recorded UNCERTAIN, never success."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import timezone

from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import ComputerAction, ComputerSession, ComputerTask
from . import hub
from . import protocol as P

HIGH_RISK = re.compile(r"\b(send|submit|delete|remove|pay|purchase|buy|place order|checkout|publish|post|transfer|confirm payment|sign out|reset password|uninstall)\b", re.I)


class Refused(Exception):
    def __init__(self, code: str, detail: str, action: ComputerAction | None = None):
        super().__init__(detail)
        self.code, self.detail, self.action = code, detail, action


def classify(action: str, params: dict, target: dict | None) -> str:
    label = " ".join(str(x) for x in ((target or {}).get("label"), (target or {}).get("text")) if x)
    if action in ("click_coordinates", "click_element", "double_click") and HIGH_RISK.search(label):
        return "high"
    if action == "key_combination" and params.get("combo") in ("ctrl+enter", "shift+delete"):
        return "high"
    if action in ("launch_application", "open_url", "drag"):
        return "medium"
    return "low" if action in P.INPUT else "none"


def digest(session_id: str, action: str, params: dict, target: dict | None) -> str:
    t = {k: (target or {}).get(k) for k in ("label", "text")}
    return hashlib.sha256(json.dumps([session_id, action, params, t], sort_keys=True).encode()).hexdigest()


def perform(db: Session, s: ComputerSession, action: str, params: dict, *, task: ComputerTask | None = None, reason: str = "", target: dict | None = None,
            actor: str = "agent", epoch: int | None = None, approved_digest: str | None = None, timeout: float = 30.0) -> tuple[ComputerAction, dict]:
    db.refresh(s)
    row = ComputerAction(tenant_id=s.tenant_id, session_id=s.id, task_id=task.id if task else None, actor=actor, action=action, params={}, reason=reason[:300],
                         target=target, before_frame_id=s.latest_frame_id)

    def refuse(code, detail, status="REFUSED"):
        row.status, row.error = status, f"{code}: {detail}"[:300]
        db.add(row)
        db.commit()
        raise Refused(code, detail, row)

    # 1-2: session ownership was checked by the caller (tenant-scoped lookup); here: state, expiry, actor rights
    exp = s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)
    if s.status in ("STOPPED", "ENDED") or exp < utcnow():
        refuse("session_closed", f"session is {s.status if s.status in ('STOPPED', 'ENDED') else 'expired'}")
    if actor == "agent" and action in P.INPUT:
        if s.status != "ACTIVE":
            refuse("not_in_control", f"session is {s.status}; the agent may not send input", "BLOCKED")
        if epoch is not None and epoch != s.control_epoch:
            refuse("control_changed", "control changed (pause, stop or takeover) since this step was planned", "BLOCKED")
    if actor == "user" and s.status != "USER_CONTROL" and action in P.INPUT:
        refuse("not_in_control", "take control first")
    # 3: schema
    try:
        params = P.validate(action, params)
    except P.InvalidAction as e:
        refuse("invalid_action", str(e))
    row.params = params
    # 4-5: permission and risk; high-impact actions need an approval bound to these exact parameters
    row.risk = classify(action, params, target)
    row.digest = digest(s.id, action, params, target)
    if actor == "agent" and row.risk == "high" and approved_digest != row.digest:
        if task:
            task.pending_approval = {"digest": row.digest, "action": action, "params": params, "target": target, "reason": reason}
            task.status = "NEEDS_APPROVAL"
        refuse("approval_required", f"'{(target or {}).get('label') or action}' changes something outside this screen; it needs your approval", "BLOCKED")
    # 6: stale state: a grounded target must come from the newest frame of this session
    if target and target.get("frame_id") and target["frame_id"] != s.latest_frame_id and _target_moved(db, target, s.latest_frame_id):
        refuse("stale_target", "the screen changed where this target was found; observe again", "BLOCKED")
    # 7: persist before acting, so a crash leaves PENDING/UNCERTAIN, never DONE
    row.status = "SENT"
    db.add(row)
    db.commit()
    try:
        res = hub.call(s.device_id, action, params, label=(target or {}).get("label", ""), timeout=timeout, actor=actor)
    except (hub.DeviceOffline, TimeoutError) as e:
        row.status = "UNCERTAIN" if action in P.INPUT else "FAILED"
        row.error = f"{type(e).__name__}: {e}"[:300]
        db.commit()
        raise Refused("device_unreachable", row.error, row)
    # 8: new observation + evidence
    obs = res.pop("observation", None)
    if obs:
        f = hub.store_frame(db, s.tenant_id, s.id, obs)
        row.after_frame_id = f.id
        res["frame_id"] = f.id
        res["frame_changed"] = bool(row.before_frame_id) and obs["sha256"] != _sha(db, row.before_frame_id)
    row.status = "DONE" if res.get("ok") else "FAILED"
    if not res.get("ok"):
        row.error = f"{res.get('error')}: {res.get('detail', '')}"[:300]
        if res.get("error") in ("paused", "stopped", "user_has_control"):
            row.status = "BLOCKED"
    db.commit()
    return row, res


def _target_moved(db, target: dict, latest_id: str | None) -> bool:
    """True if the region around the target, or the active window, differs between the target's frame and the newest frame."""
    from pathlib import Path

    import numpy as np
    from PIL import Image

    from ..models import ComputerFrame
    a, b = db.get(ComputerFrame, target["frame_id"]), db.get(ComputerFrame, latest_id) if latest_id else None
    if not a or not b:
        return True
    if (a.active_window or {}).get("title") != (b.active_window or {}).get("title") or (a.width, a.height) != (b.width, b.height):
        return True
    bb = target.get("bbox") or {}
    box = (max(bb.get("x", 0) - 12, 0), max(bb.get("y", 0) - 12, 0), min(bb.get("x", 0) + bb.get("w", 0) + 12, a.width), min(bb.get("y", 0) + bb.get("h", 0) + 12, a.height))
    ia = np.asarray(Image.open(Path(a.path)).convert("L").crop(box), dtype=np.int16)
    ib = np.asarray(Image.open(Path(b.path)).convert("L").crop(box), dtype=np.int16)
    return float(np.mean(np.abs(ia - ib) > 40)) > 0.08


def _sha(db, frame_id):
    from ..models import ComputerFrame
    f = db.get(ComputerFrame, frame_id)
    return f.sha256 if f else None
