from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import AuditEvent, AuthSession, Membership, User
from .security import hash_token, safe_equal

COOKIE = "redeem_session"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Ctx:
    user: User
    tenant_id: str
    workspace_id: str
    role: str
    session: AuthSession
    db: Session


def err(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def current_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    token = request.cookies.get(COOKIE)
    if not token:
        raise err(401, "unauthenticated", "Sign in required")
    sess = db.get(AuthSession, hash_token(token))
    if not sess or sess.expires_at <= utcnow():
        raise err(401, "session_expired", "Session expired")
    user = db.get(User, sess.user_id)
    if not user or user.deleted_at is not None:
        raise err(401, "unauthenticated", "Account unavailable")
    if request.method in MUTATING:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not safe_equal(sent, sess.csrf_token):
            raise err(403, "csrf_failed", "Missing or invalid CSRF token")
    # Tenant identity is derived here, never from request input.
    mem = db.query(Membership).filter(Membership.user_id == user.id).first()
    if not mem:
        raise err(403, "no_membership", "No workspace membership")
    return Ctx(user=user, tenant_id=mem.tenant_id, workspace_id=mem.workspace_id, role=mem.role,
               session=sess, db=db)


def audit(db: Session, ctx: Ctx | None, action: str, target: str | None = None, data: dict | None = None,
          tenant_id: str | None = None) -> None:
    db.add(AuditEvent(tenant_id=ctx.tenant_id if ctx else tenant_id, user_id=ctx.user.id if ctx else None,
                      action=action, target=target, data=data or {}))
