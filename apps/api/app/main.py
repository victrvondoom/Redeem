import logging
import secrets

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import auth, brief, cases, computer, history, integrations, memory, misc, missions, ops, privacy, skills_projects, voice, workspace
from .db import SessionLocal, init_db
from .orchestration.engine import EngineError, recover_incomplete

log = logging.getLogger("redeem")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        fixed = recover_incomplete(db)
        if fixed:
            log.warning("recovered %d interrupted dispatches", len(fixed))
        from .computer.recovery import recover as _recover_computer
        n = _recover_computer(db)
        if n:
            log.warning("marked %d interrupted computer tasks/actions uncertain", n)
    yield
    from .computer import cloud as _cloud
    _cloud.stop_all()
    from .resolve import browser as _rb
    _rb.shutdown_all()


app = FastAPI(title="REDEEM API", version="0.1.0", lifespan=lifespan)
for r in (auth.router, missions.router, voice.router, misc.router, ops.router, cases.router, workspace.router, memory.router, privacy.router, history.router, integrations.router, brief.router, skills_projects.router, computer.router):
    app.include_router(r)
from .computer import demo_crm as _demo_crm  # noqa: E402
app.include_router(_demo_crm.router)


@app.middleware("http")
async def correlation(request: Request, call_next):
    cid = request.headers.get("x-request-id") or secrets.token_hex(8)
    request.state.cid = cid
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = cid
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


def _body(request: Request, code: str, message: str, status: int, headers: dict | None = None, **extra):
    return JSONResponse({"error": {"code": code, "message": message, "correlation_id": getattr(request.state, "cid", None),
                                   **extra}}, status_code=status, headers=headers)


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    d = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return _body(request, d.pop("code", "error"), d.pop("message", ""), exc.status_code, headers=exc.headers, **d)


@app.exception_handler(EngineError)
async def engine_exc(request: Request, exc: EngineError):
    return _body(request, exc.code, exc.message, exc.status, **exc.extra)


@app.exception_handler(RequestValidationError)
async def validation_exc(request: Request, exc: RequestValidationError):
    fields = [{"loc": list(e["loc"])[1:], "msg": e["msg"]} for e in exc.errors()]
    return _body(request, "validation_error", "Request validation failed", 422, fields=fields)
