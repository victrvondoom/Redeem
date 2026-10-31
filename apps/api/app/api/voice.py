import re

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from ..config import settings
from ..core.deps import Ctx, audit, current_ctx, err
from ..core.security import limiter, safe_equal
from ..db import get_db
from ..models import Call, ConsentRecord, Mission
from ..schemas import AttachIn, ConsentIn, OutboundIn
from ..voice import bolna, provider
from ..voice.prompts import read_back
from ..voice.service import apply_call_update

router = APIRouter(prefix="/api/v1", tags=["voice"])


def _call_json(c: Call) -> dict:
    return {"id": c.id, "kind": c.kind, "status": c.status, "execution_id": c.execution_id,
            "mission_id": c.mission_id, "language": c.language, "recording_consent": c.recording_consent,
            "transcript": c.transcript, "cost": c.cost, "cost_unit": "provider-reported (unit unverified)"
            if c.cost is not None else None, "duration_seconds": c.duration_seconds, "error_code": c.error_code,
            "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(), "source": "live_provider"}


def _consented(ctx: Ctx, purpose: str) -> bool:
    row = ctx.db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == ctx.user.id,
                                                    ConsentRecord.purpose == purpose)
                        .order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc()))
    return bool(row and row.granted)


def _raise(e: bolna.BolnaError):
    raise err(e.status, e.code, str(e), scope=e.scope)


@router.get("/voice/status")
def status(ctx: Ctx = Depends(current_ctx)):
    configured = settings.bolna_configured
    return {"provider": "bolna", "state": "READY" if configured else "PROVIDER_NOT_CONFIGURED",
            "web_call": configured, "outbound": configured and settings.allow_outbound_calls
            and bool(settings.outbound_allowlist), "webhook_configured": bool(settings.bolna_webhook_secret),
            "consent": {"voice_call": _consented(ctx, "voice_call"), "call_recording": _consented(ctx, "call_recording")},
            "disclosure": "You will speak with an AI voice agent. Recording is off unless you consent separately.",
            "languages_verified_live": []}


@router.post("/voice/consent", status_code=201)
def consent(body: ConsentIn, ctx: Ctx = Depends(current_ctx)):
    ctx.db.add(ConsentRecord(tenant_id=ctx.tenant_id, user_id=ctx.user.id, purpose=body.purpose,
                             granted=body.granted))
    audit(ctx.db, ctx, "consent.set", body.purpose, {"granted": body.granted})
    ctx.db.commit()
    return {"purpose": body.purpose, "granted": body.granted}


@router.post("/voice/session")
def mint_session(request: Request, ctx: Ctx = Depends(current_ctx)):
    """Shape matches the @bolna/web-call `sessionUrl` contract: POST, JSON in, mint JSON out unchanged."""
    limiter.check(f"voice:{ctx.user.id}", 10)
    if not _consented(ctx, "voice_call"):
        raise err(403, "consent_required", "Consent to an AI voice call is required first")
    try:
        session = provider.get_provider().mint_web_session()
    except bolna.BolnaError as e:
        _raise(e)
    call = Call(tenant_id=ctx.tenant_id, user_id=ctx.user.id, kind="web", language=ctx.user.language,
                recording_consent=_consented(ctx, "call_recording"))
    ctx.db.add(call)
    audit(ctx.db, ctx, "voice.session_minted", call.id)
    ctx.db.commit()
    # Credentials are passed through to the caller and never persisted or logged.
    return JSONResponse(session, headers={"X-Redeem-Call-Id": call.id, "Cache-Control": "no-store"})


def _owned_call(ctx: Ctx, call_id: str) -> Call:
    c = ctx.db.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == ctx.tenant_id))
    if not c:
        raise err(404, "not_found", "Call not found")
    return c


@router.post("/voice/calls/{call_id}/attach")
def attach(call_id: str, body: AttachIn, ctx: Ctx = Depends(current_ctx)):
    c = _owned_call(ctx, call_id)
    if c.execution_id and c.execution_id != body.execution_id:
        raise err(409, "already_attached", "Call already correlated to another execution")
    taken = ctx.db.scalar(select(Call.id).where(Call.provider == "bolna", Call.execution_id == body.execution_id,
                                                Call.id != c.id))
    if taken:
        raise err(409, "execution_in_use", "Execution id already correlated")
    c.execution_id = body.execution_id
    ctx.db.commit()
    return _call_json(c)


@router.post("/voice/calls/outbound", status_code=201)
def outbound(body: OutboundIn, ctx: Ctx = Depends(current_ctx)):
    limiter.check(f"outbound:{ctx.user.id}", 5)
    if not settings.allow_outbound_calls:
        raise err(403, "outbound_disabled", "Outbound calling is disabled for this deployment")
    if body.phone not in settings.outbound_allowlist:
        raise err(403, "destination_not_authorised", "Only operator-authorised test numbers can be dialled")
    if not _consented(ctx, "voice_call"):
        raise err(403, "consent_required", "Consent to an AI voice call is required first")
    if body.mission_id and not ctx.db.scalar(select(Mission.id).where(Mission.id == body.mission_id,
                                                                      Mission.tenant_id == ctx.tenant_id)):
        raise err(404, "not_found", "Mission not found")
    try:
        data = provider.get_provider().start_outbound(body.phone, {"language": body.language,
                                                               "ai_disclosure": "This is an AI assistant."})
    except bolna.BolnaError as e:
        _raise(e)
    ex = data.get("execution_id") or data.get("run_id")
    call = Call(tenant_id=ctx.tenant_id, user_id=ctx.user.id, kind="outbound", mission_id=body.mission_id,
                execution_id=str(ex) if ex else None, language=body.language, status="queued", status_rank=1,
                recording_consent=_consented(ctx, "call_recording"))
    ctx.db.add(call)
    audit(ctx.db, ctx, "voice.outbound_started", call.id)  # destination deliberately not logged
    ctx.db.commit()
    return _call_json(call)


@router.get("/voice/calls")
def list_calls(ctx: Ctx = Depends(current_ctx), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = ctx.db.scalars(select(Call).where(Call.tenant_id == ctx.tenant_id)
                          .order_by(Call.created_at.desc()).limit(limit).offset(offset))
    return {"items": [_call_json(c) for c in rows]}


@router.get("/voice/calls/{call_id}")
def get_call(call_id: str, ctx: Ctx = Depends(current_ctx)):
    return _call_json(_owned_call(ctx, call_id))


@router.post("/voice/calls/{call_id}/sync")
def sync_call(call_id: str, ctx: Ctx = Depends(current_ctx)):
    c = _owned_call(ctx, call_id)
    if not c.execution_id:
        raise err(409, "not_correlated", "Call has no provider execution id yet")
    try:
        data = provider.get_provider().get_execution(c.execution_id)
    except bolna.BolnaError as e:
        _raise(e)
    outcome = apply_call_update(ctx.db, c, data, authoritative=True)
    ctx.db.commit()
    return {**_call_json(c), "sync": outcome}


@router.post("/webhooks/bolna", status_code=202)
async def bolna_webhook(request: Request, token: str = Query("", max_length=200), db=Depends(get_db)):
    """Machine ingress, separate from end-user auth. Bolna's signing scheme is not assumed: the endpoint is
    gated by a private shared secret AND every event is confirmed by reading the execution back from Bolna.
    A webhook can only update call bookkeeping; it can never create, approve or execute an action."""
    if not settings.bolna_webhook_secret:
        raise err(503, "webhook_not_configured", "Webhook ingress is not configured")
    if not safe_equal(token, settings.bolna_webhook_secret):
        raise err(401, "invalid_webhook_token", "Invalid webhook credentials")
    allowed = {ip.strip() for ip in settings.bolna_webhook_allowed_ips.split(",") if ip.strip()}
    if allowed:
        src = request.client.host if request.client else ""
        if settings.trust_forwarded_for and request.headers.get("x-forwarded-for"):
            src = request.headers["x-forwarded-for"].split(",")[0].strip()
        if src not in allowed:
            raise err(403, "source_not_allowed", "Source address is not allowed")
    raw = await request.body()
    if len(raw) > 256_000:
        raise err(413, "payload_too_large", "Payload too large")
    try:
        payload = await request.json()
    except ValueError:
        raise err(422, "invalid_payload", "Body must be JSON")
    if not isinstance(payload, dict):
        raise err(422, "invalid_payload", "Body must be a JSON object")
    ex = payload.get("id") or payload.get("execution_id")
    if not isinstance(ex, str) or not ex:
        raise err(422, "invalid_payload", "Missing execution id")
    call = db.scalar(select(Call).where(Call.provider == "bolna", Call.execution_id == ex))
    if not call:
        return {"accepted": False, "reason": "unknown_execution"}
    try:
        authoritative_data = provider.get_provider().get_execution(ex)
        outcome = apply_call_update(db, call, authoritative_data, authoritative=True)
    except bolna.BolnaError:
        outcome = apply_call_update(db, call, {"status": str(payload.get("status", "unknown")), "unverified": True},
                                    authoritative=False)
    db.commit()
    return {"accepted": True, "result": outcome}


# ---------------------------------------------------------------- function-calling tools for the Bolna agent
from ..models import FxBooking, FxProduct, Membership, User  # noqa: E402
from ..orchestration import engine  # noqa: E402


@router.post("/voice/tools/{tool}")
async def voice_tool(tool: str, request: Request, token: str = Query("", max_length=200), db=Depends(get_db)):
    """Webhook tools the Bolna agent may call mid-conversation. Gated by the private secret; tenant is derived from the
    call row, never from the payload. Tools are read-only except start_mission, which only *plans*: approval and
    execution still require the signed-in human."""
    if not settings.bolna_webhook_secret:
        raise err(503, "webhook_not_configured", "Tool ingress is not configured")
    if not safe_equal(token, settings.bolna_webhook_secret):
        raise err(401, "invalid_webhook_token", "Invalid credentials")
    body = await request.json()
    ex = body.get("execution_id")
    args = body.get("args") or {k: v for k, v in body.items() if k != "execution_id"}  # Bolna sends flat parameters
    call = db.scalar(select(Call).where(Call.provider == "bolna", Call.execution_id == str(ex))) if ex else None
    if not call:
        raise err(404, "unknown_call", "No such call")
    t = call.tenant_id
    if tool == "search_catalogue":
        q = str(args.get("query", ""))[:80].lower()
        rows = [p for p in db.scalars(select(FxProduct).where(FxProduct.tenant_id == t)) if q and q in p.name.lower()]
        return {"results": [{"id": p.id, "name": p.name, "price_inr": p.price_paise / 100, "in_stock": p.stock} for p in rows]}
    if tool == "lookup_booking":
        b = db.scalar(select(FxBooking).where(FxBooking.tenant_id == t, FxBooking.ref == str(args.get("ref", ""))[:12]))
        return {"found": bool(b), **({"ref": b.ref, "status": b.status, "refund_status": b.refund_status} if b else {})}
    if tool in ("save_answer", "recall"):
        from types import SimpleNamespace

        from ..memory import service as mem
        from ..models import ConsentRecord as CR
        owner = db.get(User, call.user_id)
        c = db.scalar(select(CR).where(CR.user_id == call.user_id, CR.purpose == "memory_capture").order_by(CR.created_at.desc(), CR.id.desc()))
        if not (c and c.granted):
            return {"saved": False, "reason": "memory_capture_consent_not_granted"}
        mctx = SimpleNamespace(tenant_id=t, user=owner)
        if tool == "recall":
            return {"items": [{"field": r["field"], "value": r["value"]} for r in mem.relevant(db, mctx, str(args.get("topic", ""))[:200])]}
        from ..memory import context as _cx
        _cx.record(db, mctx, "voice", "user", str(args.get("utterance", ""))[:1000], call.id)
        r = mem.ingest(db, mctx, str(args.get("utterance", ""))[:1000], str(args["field"])[:60] if args.get("field") else None, "bolna_call", call.id, str(args.get("segment", ""))[:40] or None)
        if r["clarification"]:
            _cx.record(db, mctx, "voice", "assistant", r["clarification"], call.id)
        db.commit()
        return {"saved": [s["field"] for s in r["saved"]], "needs_confirmation": r["needs_confirmation"], "ambiguous": r["ambiguous"], "ask_user": r["clarification"]}
    if tool == "start_mission":
        intent = str(args.get("intent", ""))[:2000]
        if len(intent) < 3:
            raise err(422, "invalid_args", "intent required")
        user = db.get(User, call.user_id)
        ws = db.scalar(select(Membership.workspace_id).where(Membership.user_id == call.user_id))
        m = Mission(tenant_id=t, workspace_id=ws, user_id=call.user_id, intent=intent, source="voice", language_selected=user.language if user else "en")
        db.add(m)
        db.flush()
        try:
            engine.start_mission(db, m)
        finally:
            db.commit()
        call.mission_id = m.id
        db.commit()
        return {"mission_id": m.id, "status": m.status, "needs": (m.clarification or {}).get("message"),
                "plan_summary": (m.plan or {}).get("summary"), "note": "Awaiting the user's approval in the REDEEM app."}
    if tool in ("mission_reply", "read_back_plan", "interrupt"):
        m = db.get(Mission, call.mission_id) if call.mission_id else None
        if not m or m.tenant_id != t:
            raise err(409, "no_active_mission", "This call has no active mission yet; call start_mission first")
        user = db.get(User, call.user_id)
        if tool == "read_back_plan":
            acts = (m.plan or {}).get("actions", [])
            pend = [a for a in acts if a["status"] == "AWAITING_APPROVAL"]
            if not pend:
                return {"spoken": None, "note": "Nothing awaiting approval.", "status": m.status}
            a = pend[0] if not args.get("second") else pend[min(1, len(pend) - 1)]
            p = a["params"]
            who = p.get("passenger_name") or p.get("customer_name") or p.get("lead_name") or p.get("contact_name") or p.get("title") or a["kind"]
            amt = f"₹{a['amount_paise'] / 100:,.2f}" if a.get("amount_paise") else None
            return {"spoken": read_back(m.language_selected, a["kind"].replace("_", " "), str(who), amt), "can_approve_by_voice": False, "status": m.status}
        if tool == "interrupt":
            engine.pause(db, m)
            engine.emit(db, m, "VOICE_INTERRUPT", {"call": call.id})
            db.commit()
            return {"paused": True, "note": "Stopped. Tell me the new instruction; nothing further will run until you resume in the app."}
        text = str(args.get("text", ""))[:500]
        ref = engine.resolve_reference(m, text)
        try:
            if ref:
                engine.bind(db, m, ref[0], ref[1])
            elif re.search(r"\b(actually|instead|wait|no,|change|don't|do not)\b", text, re.I):
                engine.revise(db, m, intent=f"{m.intent}. Correction: {text}", reason="voice_correction")
            else:
                return {"understood": False, "ask": "Which one do you mean? You can say 'the second option' or give the name."}
        finally:
            db.commit()
        return {"understood": True, "status": m.status, "revision": m.revision, "needs": (m.clarification or {}).get("message")}
    raise err(404, "unknown_tool", "Unknown tool")
