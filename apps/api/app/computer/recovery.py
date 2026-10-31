"""After a restart nothing in flight is assumed to have worked: actions that were sent become UNCERTAIN, running tasks
stop with an explanation, and cloud computers (whose processes died with the server) are ended."""
from sqlalchemy import select

from ..db import utcnow
from ..models import ComputerAction, ComputerDevice, ComputerSession, ComputerTask


def recover(db) -> int:
    n = 0
    for a in db.scalars(select(ComputerAction).where(ComputerAction.status.in_(["PENDING", "SENT"]))):
        a.status, a.error = "UNCERTAIN", "server restarted before the device answered; check the screen before repeating"
        n += 1
    for t in db.scalars(select(ComputerTask).where(ComputerTask.status.in_(["PLANNING", "RUNNING", "PAUSED", "USER_CONTROL"]))):
        t.status = "UNCERTAIN"
        t.report = {**(t.report or {}), "summary": "The server restarted during this task. Some steps may have happened; look at the screen and run it again if needed."}
        n += 1
    for d in db.scalars(select(ComputerDevice).where(ComputerDevice.kind == "cloud", ComputerDevice.status == "PAIRED")):
        d.status, d.revoked_at = "REVOKED", utcnow()
        for s in db.scalars(select(ComputerSession).where(ComputerSession.device_id == d.id, ComputerSession.status.in_(["ACTIVE", "PAUSED", "USER_CONTROL"]))):
            s.status, s.ended_at = "ENDED", utcnow()
    db.commit()
    return n
