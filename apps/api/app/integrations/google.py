"""Google adapter (OAuth 2.0 web-server flow, Calendar v3, Gmail v1) using the documented public endpoints.
Only real HTTP calls; nothing is simulated here. The transport is injectable so contract tests can run offline; those tests are labelled as such
and are NOT evidence of a live connection."""
from __future__ import annotations

import base64
import time
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105
REVOKE = "https://oauth2.googleapis.com/revoke"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
CAL = "https://www.googleapis.com/calendar/v3"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = {"calendar": ["https://www.googleapis.com/auth/calendar.events"],
          "email": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]}
BASE_SCOPES = ["openid", "email"]


class ProviderError(Exception):
    def __init__(self, kind: str, status: int = 0, message: str = ""):
        super().__init__(message or kind)
        self.kind, self.status, self.message = kind, status, message  # kind: auth | rate_limited | permanent | transient | uncertain | conflict | not_found


def classify(status: int) -> str:
    return {401: "auth", 403: "permanent", 404: "not_found", 409: "conflict", 429: "rate_limited"}.get(status, "transient" if status >= 500 else "permanent")


class GoogleClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self.cid, self.secret, self.redirect, self.timeout, self.transport = client_id, client_secret, redirect_uri, timeout, transport

    def _http(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport)

    def _call(self, method: str, url: str, retries: int = 2, retry_unsafe: bool = False, **kw) -> httpx.Response:
        """Retries only 429/5xx on reads (or when retry_unsafe); a timeout or connection error on a write raises 'uncertain' so the caller reconciles instead of resending."""
        safe = method in ("GET", "HEAD") or retry_unsafe
        for attempt in range(retries + 1):
            try:
                with self._http() as c:
                    r = c.request(method, url, **kw)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                if safe and attempt < retries:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                raise ProviderError("uncertain" if not safe else "transient", 0, type(e).__name__)
            if r.status_code in (429, 500, 502, 503, 504) and safe and attempt < retries:
                time.sleep(min(2.0, float(r.headers.get("retry-after", 0.3 * (attempt + 1)) or 0.3)))
                continue
            return r
        raise ProviderError("transient")

    # ---- OAuth
    def auth_url(self, state: str, caps: list[str]) -> str:
        scopes = BASE_SCOPES + [s for c in caps for s in SCOPES[c]]
        q = {"client_id": self.cid, "redirect_uri": self.redirect, "response_type": "code", "scope": " ".join(scopes), "access_type": "offline",
             "prompt": "consent", "include_granted_scopes": "true", "state": state}
        return AUTH + "?" + urlencode(q)

    def _token(self, data: dict) -> dict:
        r = self._call("POST", TOKEN, retry_unsafe=True, data={"client_id": self.cid, "client_secret": self.secret, **data})
        if r.status_code != 200:
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise ProviderError("auth" if j.get("error") in ("invalid_grant", "invalid_client", "unauthorized_client") else classify(r.status_code), r.status_code, str(j.get("error", "")))
        return r.json()

    def exchange_code(self, code: str) -> dict:
        return self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect})

    def refresh(self, refresh_token: str) -> dict:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def revoke(self, token: str) -> bool:
        r = self._call("POST", REVOKE, retry_unsafe=True, data={"token": token})
        return r.status_code == 200

    def userinfo(self, access: str) -> dict:
        r = self._call("GET", USERINFO, headers={"authorization": f"Bearer {access}"})
        if r.status_code != 200:
            raise ProviderError(classify(r.status_code), r.status_code)
        return r.json()

    # ---- Calendar
    @staticmethod
    def event_id(action_id: str) -> str:
        """Calendar event ids must be 5-1024 chars of a-v and 0-9 (base32hex): deterministic from the action id so a duplicate insert is a 409, never a second event."""
        return base64.b32hexencode(action_id.encode()).decode().lower().rstrip("=")

    def calendar_insert(self, access: str, action_id: str, p: dict) -> dict:
        body = {"id": self.event_id(action_id), "summary": p["summary"], "description": p.get("description", ""),
                "start": {"dateTime": p["start"], "timeZone": p.get("timezone", "UTC")}, "end": {"dateTime": p["end"], "timeZone": p.get("timezone", "UTC")}}
        if p.get("attendees"):
            body["attendees"] = [{"email": a} for a in p["attendees"]]
        r = self._call("POST", f"{CAL}/calendars/primary/events", headers={"authorization": f"Bearer {access}"}, json=body)
        if r.status_code in (200, 201):
            return r.json()
        raise ProviderError(classify(r.status_code), r.status_code, (r.json().get("error", {}) or {}).get("message", "") if r.headers.get("content-type", "").startswith("application/json") else "")

    def calendar_get(self, access: str, event_id: str) -> dict | None:
        r = self._call("GET", f"{CAL}/calendars/primary/events/{event_id}", headers={"authorization": f"Bearer {access}"})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        raise ProviderError(classify(r.status_code), r.status_code)

    # ---- Gmail
    @staticmethod
    def build_mime(sender: str, p: dict, message_id: str) -> str:
        m = EmailMessage()
        m["To"], m["Subject"], m["Message-ID"] = ", ".join(p["to"]), p["subject"], message_id
        if sender:
            m["From"] = sender
        m.set_content(p["body"])
        return base64.urlsafe_b64encode(m.as_bytes()).decode()

    def gmail_send(self, access: str, raw: str) -> dict:
        r = self._call("POST", f"{GMAIL}/messages/send", headers={"authorization": f"Bearer {access}"}, json={"raw": raw})
        if r.status_code == 200:
            return r.json()
        raise ProviderError(classify(r.status_code), r.status_code)

    def gmail_get(self, access: str, mid: str) -> dict | None:
        r = self._call("GET", f"{GMAIL}/messages/{mid}", params={"format": "metadata", "metadataHeaders": "Message-ID"}, headers={"authorization": f"Bearer {access}"})
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        raise ProviderError(classify(r.status_code), r.status_code)

    def gmail_find_by_message_id(self, access: str, message_id: str) -> dict | None:
        r = self._call("GET", f"{GMAIL}/messages", params={"q": f"rfc822msgid:{message_id.strip('<>')}"}, headers={"authorization": f"Bearer {access}"})
        if r.status_code != 200:
            raise ProviderError(classify(r.status_code), r.status_code)
        ms = r.json().get("messages") or []
        return ms[0] if ms else None
