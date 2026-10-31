from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.deps import COOKIE, Ctx, audit, current_ctx, err
from ..core.security import hash_password, hash_token, limiter, new_token, verify_password
from ..db import get_db, utcnow
from ..fixtures.seed import seed_tenant
from ..models import AuthSession, Membership, Tenant, User, Workspace
from ..schemas import LangIn, LoginIn, RegisterIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_DUMMY = hash_password("not-a-real-password")


def _open_session(db: Session, user: User, response: Response) -> str:
    token, csrf = new_token(), new_token()
    ttl = timedelta(hours=settings.session_ttl_hours)
    db.add(AuthSession(id=hash_token(token), user_id=user.id, csrf_token=csrf, expires_at=utcnow() + ttl))
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                        max_age=int(ttl.total_seconds()), path="/")
    return csrf


def _me(ctx_user: User, tenant_id: str, workspace_id: str, role: str, csrf: str) -> dict:
    return {"id": ctx_user.id, "email": ctx_user.email, "name": ctx_user.name, "language": ctx_user.language,
            "tenant_id": tenant_id, "workspace_id": workspace_id, "role": role, "csrf_token": csrf}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.check(f"reg:{request.client.host if request.client else '-'}", settings.register_rate_limit_per_minute)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise err(409, "email_taken", "An account with this email already exists")
    user = User(email=body.email, name=body.name.strip(), password_hash=hash_password(body.password),
                language=body.language)
    tenant = Tenant(name=f"{body.name.strip()}'s workspace")
    db.add_all([user, tenant])
    db.flush()
    ws = Workspace(tenant_id=tenant.id, name="Main")
    db.add(ws)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, workspace_id=ws.id, role="owner"))
    if settings.demo_enabled:  # demo fixtures (simulated bookings, shop, CRM) are never seeded into a production workspace
        seed_tenant(db, tenant.id)
    csrf = _open_session(db, user, response)
    audit(db, None, "auth.register", user.id, tenant_id=tenant.id)
    db.commit()
    return _me(user, tenant.id, ws.id, "owner", csrf)


@router.post("/demo", status_code=201)
def demo_sign_in(request: Request, response: Response, db: Session = Depends(get_db)):
    """One-click demo: a fresh, isolated workspace seeded with the labelled practice data. Off whenever demo fixtures are off (production)."""
    if not settings.demo_enabled:
        raise err(404, "demo_disabled", "Demo sign-in is turned off on this server")
    limiter.check(f"demo:{request.client.host if request.client else '-'}", settings.register_rate_limit_per_minute)
    tag = new_token()[:10].lower()
    user = User(email=f"demo-{tag}@demo.redeem.invalid", name="Demo user", password_hash=hash_password(new_token()), language="en")
    tenant = Tenant(name="Demo workspace")
    db.add_all([user, tenant])
    db.flush()
    ws = Workspace(tenant_id=tenant.id, name="Main")
    db.add(ws)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, workspace_id=ws.id, role="owner"))
    seed_tenant(db, tenant.id)
    csrf = _open_session(db, user, response)
    audit(db, None, "auth.demo", user.id, tenant_id=tenant.id)
    db.commit()
    return _me(user, tenant.id, ws.id, "owner", csrf)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "-"
    limiter.check(f"login:{ip}:{body.email.lower()}", 8)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY)
    if not user or not ok or user.deleted_at is not None:
        raise err(401, "invalid_credentials", "Email or password is incorrect")
    mem = db.query(Membership).filter(Membership.user_id == user.id).first()
    csrf = _open_session(db, user, response)
    audit(db, None, "auth.login", user.id, tenant_id=mem.tenant_id)
    db.commit()
    return _me(user, mem.tenant_id, mem.workspace_id, mem.role, csrf)


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: Ctx = Depends(current_ctx)):
    ctx.db.delete(ctx.session)
    audit(ctx.db, ctx, "auth.logout")
    ctx.db.commit()
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(ctx: Ctx = Depends(current_ctx)):
    return _me(ctx.user, ctx.tenant_id, ctx.workspace_id, ctx.role, ctx.session.csrf_token)


@router.patch("/language")
def set_language(body: LangIn, ctx: Ctx = Depends(current_ctx)):
    ctx.user.language = body.language
    ctx.db.commit()
    return {"language": ctx.user.language}
