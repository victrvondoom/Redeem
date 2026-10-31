from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta

from sqlalchemy import delete, select, update

from ..config import settings
from ..connectors.base import canonical
from ..db import utcnow
from ..models import Call, ExternalAction, Integration, OAuthState
from ..security import vault
from . import google as g

CAPS_SCOPE = {"calendar": "https://www.googleapis.com/auth/calendar.events", "email": "https://www.googleapis.com/auth/gmail.send"}
make_google = lambda: g.GoogleClient(settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri, 10.0)  # noqa: E731


class IntegrationError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def google_missing() -> list[str]:
    return [n for n, v in (("GOOGLE_OAUTH_CLIENT_ID", settings.google_client_id), ("GOOGLE_OAUTH_CLIENT_SECRET", settings.google_client_secret),
                           ("GOOGLE_OAUTH_REDIRECT_URI", settings.google_redirect_uri)) if not v]


def _tokens(db, tenant: str, i: Integration) -> dict:
    return json.loads(vault.decrypt_str(db, tenant, i.token_enc))


def _get(db, tenant: str) -> Integration | None:
    return db.scalar(select(Integration).where(Integration.tenant_id == tenant, Integration.provider == "google"))


def status(db, ctx) -> dict:
    gi = _get(db, ctx.tenant_id)
    gm = google_missing()
    calls = list(db.scalars(select(Call).where(Call.tenant_id == ctx.tenant_id, Call.provider == "bolna")))
    bm = [n for n, v in (("BOLNA_API_KEY", settings.bolna_api_key), ("BOLNA_AGENT_ID", settings.bolna_agent_id), ("BOLNA_WEBHOOK_SECRET", settings.bolna_webhook_secret)) if not v]
    return {"providers": [
        {"provider": "google", "label": "Google Calendar and Gmail", "auth": "OAuth 2.0 (authorization code, offline access)", "configured": not gm, "missing_config": gm,
         "state": ("not_configured" if gm else (gi.status if gi else "not_connected")), "account": gi.account_label if gi else None, "scopes": gi.scopes if gi else [],
         "last_verified_at": gi.last_verified_at.isoformat() if gi and gi.last_verified_at else None, "last_error": gi.last_error if gi else None,
         "operations": ["calendar.create_event (idempotent, read-back verified)", "email.send (read-back verified, never resent after an uncertain outcome)"],
         "needs": "Create an OAuth client in Google Cloud Console, add the redirect URI, then set the three variables." if gm else ("Press Connect." if not gi or gi.status != "connected" else None),
         "live_verified": bool(gi and gi.status == "connected" and gi.last_verified_at)},
        {"provider": "bolna", "label": "Bolna voice", "auth": "API key (server side) plus webhook secret", "configured": settings.bolna_configured, "missing_config": bm,
         "state": "configured" if settings.bolna_configured else "not_configured", "account": None, "scopes": ["voice:web_call", "voice:outbound"],
         "last_verified_at": max((c.updated_at for c in calls if c.status_rank > 0), default=None).isoformat() if any(c.status_rank > 0 for c in calls) else None, "last_error": None,
         "operations": ["web session", "outbound call", "execution read-back", "webhook with read-back", "agent tools save_answer/recall"],
         "needs": None if settings.bolna_configured else "Set BOLNA_API_KEY, BOLNA_AGENT_ID and BOLNA_WEBHOOK_SECRET.",
         "live_verified": any(c.status_rank > 0 and c.execution_id for c in calls), "calls_recorded": len(calls)}]}


def connect_start(db, ctx, caps: list[str]) -> str:
    if google_missing():
        raise IntegrationError("PROVIDER_NOT_CONFIGURED", f"Missing configuration: {', '.join(google_missing())}", 503)
    state = secrets.token_urlsafe(32)
    db.execute(delete(OAuthState).where(OAuthState.expires_at <= utcnow()))
    db.add(OAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(), tenant_id=ctx.tenant_id, user_id=ctx.user.id, provider="google", scopes=caps, expires_at=utcnow() + timedelta(minutes=10)))
    db.flush()
    return make_google().auth_url(state, caps)


def callback(db, ctx, state: str, code: str) -> Integration:
    row = db.get(OAuthState, hashlib.sha256(state.encode()).hexdigest())
    if not row or row.expires_at <= utcnow() or row.user_id != ctx.user.id or row.tenant_id != ctx.tenant_id:
        raise IntegrationError("invalid_state", "The sign-in attempt is invalid or expired. Start again.", 400)
    db.delete(row)  # single use
    db.flush()
    cl = make_google()
    try:
        tok = cl.exchange_code(code)
        who = cl.userinfo(tok["access_token"])
    except g.ProviderError as e:
        raise IntegrationError("provider_" + e.kind, f"Google rejected the authorization ({e.message or e.kind}).", 502)
    if not tok.get("refresh_token"):
        raise IntegrationError("no_refresh_token", "Google did not return offline access. Remove REDEEM from your Google account permissions and connect again.", 400)
    blob = {"access": tok["access_token"], "refresh": tok["refresh_token"], "expires_at": (utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)))).timestamp()}
    gi = _get(db, ctx.tenant_id)
    if not gi:
        gi = Integration(tenant_id=ctx.tenant_id, user_id=ctx.user.id, provider="google", token_enc="x")
        db.add(gi)
    gi.token_enc, gi.status, gi.scopes = vault.encrypt_str(db, ctx.tenant_id, json.dumps(blob)), "connected", sorted(set(str(tok.get("scope", "")).split()))
    gi.account_label, gi.last_verified_at, gi.last_error = who.get("email"), utcnow(), None
    db.flush()
    return gi


def access_token(db, ctx, gi: Integration) -> str:
    if gi.status != "connected":
        raise IntegrationError("not_connected", "Google is not connected.", 409)
    b = _tokens(db, ctx.tenant_id, gi)
    if b["expires_at"] - utcnow().timestamp() > 60:
        return b["access"]
    try:
        t = make_google().refresh(b["refresh"])
    except g.ProviderError as e:
        if e.kind == "auth":
            gi.status, gi.last_error = "error", "reauthorization_required"
            db.flush()
            raise IntegrationError("reauthorization_required", "Google no longer accepts the saved authorization. Reconnect.", 409)
        raise IntegrationError("provider_" + e.kind, "Google is temporarily unavailable.", 502)
    b.update(access=t["access_token"], expires_at=(utcnow() + timedelta(seconds=int(t.get("expires_in", 3600)))).timestamp())
    gi.token_enc = vault.encrypt_str(db, ctx.tenant_id, json.dumps(b))
    db.flush()
    return b["access"]


def test_connection(db, ctx) -> dict:
    gi = _get(db, ctx.tenant_id)
    if not gi:
        raise IntegrationError("not_connected", "Google is not connected.", 409)
    tok = access_token(db, ctx, gi)
    try:
        who = make_google().userinfo(tok)
    except g.ProviderError as e:
        gi.last_error = e.kind
        raise IntegrationError("provider_" + e.kind, "The connection test failed.", 502)
    gi.last_verified_at, gi.last_error, gi.account_label = utcnow(), None, who.get("email", gi.account_label)
    return {"ok": True, "account": gi.account_label, "verified_at": gi.last_verified_at.isoformat()}


def disconnect(db, ctx) -> dict:
    gi = _get(db, ctx.tenant_id)
    if not gi:
        raise IntegrationError("not_connected", "Google is not connected.", 404)
    revoked = None
    try:
        b = _tokens(db, ctx.tenant_id, gi)
        revoked = make_google().revoke(b.get("refresh") or b.get("access", ""))
    except Exception:  # noqa: BLE001 - local revocation must happen even if Google is unreachable
        revoked = False
    gi.token_enc, gi.status, gi.scopes = vault.encrypt_str(db, ctx.tenant_id, "{}"), "revoked", []
    n = db.execute(update(ExternalAction).where(ExternalAction.tenant_id == ctx.tenant_id, ExternalAction.provider == "google", ExternalAction.status.in_(["DRAFT", "APPROVED"]))
                   .values(status="FAILED", error="connection_revoked")).rowcount
    return {"revoked_at_provider": revoked, "local_credentials_cleared": True, "queued_actions_stopped": n}


# ---------------------------------------------------------------- actions
KINDS = {"calendar.create_event": ("calendar", CAPS_SCOPE["calendar"]), "email.send": ("email", CAPS_SCOPE["email"])}


def _digest(provider: str, kind: str, params: dict, account: str | None) -> str:
    return hashlib.sha256(canonical({"p": provider, "k": kind, "params": params, "account": account}).encode()).hexdigest()


def create_action(db, ctx, kind: str, params: dict) -> ExternalAction:
    if kind not in KINDS:
        raise IntegrationError("unsupported_operation", "Unsupported operation.", 422)
    gi = _get(db, ctx.tenant_id)
    if not gi or gi.status != "connected":
        raise IntegrationError("PROVIDER_NOT_CONFIGURED" if google_missing() else "not_connected", "Connect Google first." if not google_missing() else f"Missing configuration: {', '.join(google_missing())}", 409)
    if KINDS[kind][1] not in gi.scopes:
        raise IntegrationError("missing_scope", f"This connection was not granted {KINDS[kind][0]} access. Reconnect with it enabled.", 409)
    a = ExternalAction(tenant_id=ctx.tenant_id, user_id=ctx.user.id, provider="google", kind=kind, params_enc=vault.encrypt_str(db, ctx.tenant_id, json.dumps(params)),
                       digest=_digest("google", kind, params, gi.account_label), status="DRAFT")
    db.add(a)
    db.flush()
    return a


def get_action(db, ctx, action_id: str) -> ExternalAction | None:
    a = db.get(ExternalAction, action_id)
    return a if a and a.tenant_id == ctx.tenant_id else None


def action_json(db, ctx, a: ExternalAction) -> dict:
    return {"id": a.id, "provider": a.provider, "kind": a.kind, "params": json.loads(vault.decrypt_str(db, ctx.tenant_id, a.params_enc)), "digest": a.digest, "status": a.status,
            "provider_ref": a.provider_ref, "verification": a.verification, "error": a.error, "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat()}


def approve(db, ctx, a: ExternalAction, digest: str) -> ExternalAction:
    if a.status != "DRAFT":
        raise IntegrationError("invalid_state", f"Only a draft can be approved (this is {a.status}).", 409)
    gi = _get(db, ctx.tenant_id)
    params = json.loads(vault.decrypt_str(db, ctx.tenant_id, a.params_enc))
    if digest != a.digest or a.digest != _digest("google", a.kind, params, gi.account_label if gi else None):
        raise IntegrationError("stale_approval", "The approval does not match the action as it now stands (changed target or account).", 409)
    a.status = "APPROVED"
    db.flush()
    return a


def _mid(a: ExternalAction) -> str:
    return f"<{a.id}@redeem.invalid>"


def _verify(db, ctx, a: ExternalAction, tok: str, params: dict) -> None:
    cl = make_google()
    try:
        if a.kind == "calendar.create_event":
            ev = cl.calendar_get(tok, a.provider_ref)
            ok = bool(ev) and ev.get("status") != "cancelled" and ev.get("summary") == params["summary"]
            a.verification = {"method": "calendar.events.get", "found": bool(ev), "summary_matches": bool(ev) and ev.get("summary") == params["summary"], "status": (ev or {}).get("status")}
        else:
            m = cl.gmail_get(tok, a.provider_ref)
            ok = bool(m) and "SENT" in (m.get("labelIds") or [])
            a.verification = {"method": "gmail.messages.get", "found": bool(m), "labelled_sent": bool(m) and "SENT" in (m.get("labelIds") or [])}
        a.status = "VERIFIED" if ok else "UNVERIFIED"
    except g.ProviderError as e:
        a.verification, a.status = {"method": "read-back", "error": e.kind}, "UNVERIFIED"


def execute(db, ctx, a: ExternalAction) -> ExternalAction:
    r = db.execute(update(ExternalAction).where(ExternalAction.id == a.id, ExternalAction.tenant_id == ctx.tenant_id, ExternalAction.status == "APPROVED").values(status="EXECUTING"))
    if r.rowcount != 1:
        raise IntegrationError("invalid_state", f"Only an approved action can run (this is {a.status}). It will not run twice.", 409)
    db.commit()
    db.refresh(a)
    gi = _get(db, ctx.tenant_id)
    params = json.loads(vault.decrypt_str(db, ctx.tenant_id, a.params_enc))
    cl = make_google()
    try:
        tok = access_token(db, ctx, gi)
        if a.kind == "calendar.create_event":
            try:
                ev = cl.calendar_insert(tok, a.id, params)
                a.provider_ref = ev["id"]
            except g.ProviderError as e:
                if e.kind != "conflict":
                    raise
                a.provider_ref = cl.event_id(a.id)  # same deterministic id already exists: reconcile, do not duplicate
                a.verification = {"note": "event with this id already existed (idempotent replay)"}
        else:
            sent = cl.gmail_send(tok, cl.build_mime(gi.account_label or "", params, _mid(a)))
            a.provider_ref = sent["id"]
        _verify(db, ctx, a, tok, params)
    except IntegrationError as e:
        a.status, a.error = "FAILED", e.code
    except g.ProviderError as e:
        if e.kind == "uncertain" or (a.kind == "email.send" and e.kind in ("transient", "rate_limited") and e.status >= 500):
            a.status, a.error = "UNCERTAIN", "outcome_unknown_reconcile_before_any_retry"
        elif e.kind == "auth":
            a.status, a.error = "FAILED", "reauthorization_required"
            gi.status, gi.last_error = "error", "reauthorization_required"
        else:
            a.status, a.error = "FAILED", f"provider_{e.kind}"
    db.flush()
    return a


def reconcile(db, ctx, a: ExternalAction) -> ExternalAction:
    """Read-only lookup of an UNCERTAIN action. Never resends."""
    if a.status != "UNCERTAIN":
        raise IntegrationError("invalid_state", "Only an uncertain action can be reconciled.", 409)
    gi = _get(db, ctx.tenant_id)
    params = json.loads(vault.decrypt_str(db, ctx.tenant_id, a.params_enc))
    cl = make_google()
    try:
        tok = access_token(db, ctx, gi)
        if a.kind == "calendar.create_event":
            a.provider_ref = cl.event_id(a.id)
            found = cl.calendar_get(tok, a.provider_ref)
        else:
            hit = cl.gmail_find_by_message_id(tok, _mid(a))
            found, a.provider_ref = hit, (hit or {}).get("id")
    except (IntegrationError, g.ProviderError):
        a.verification = {"method": "reconcile", "error": "lookup_failed_try_again"}
        db.flush()
        return a
    if found:
        _verify(db, ctx, a, tok, params)
        a.error = None
    else:
        a.status, a.error, a.verification = "FAILED", "not_found_at_provider", {"method": "reconcile", "found": False, "note": "Nothing was created. You may create a new draft."}
    db.flush()
    return a
