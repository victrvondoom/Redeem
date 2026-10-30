"""Bolna provider adapter.

Contract sources:
- Browser session mint: POST {base}/web-call/freeswitch-session  {agent_id, user_data?}  -> returned to the
  browser as-is (documented in the published @bolna/web-call README, v3.0.1). The API key never leaves the server.
- Outbound call: POST {base}/call and execution read-back: GET {base}/executions/{id}. docs.bolna.ai was not
  reachable from the build sandbox, so these two are implemented from the public API shape and are marked
  UNVERIFIED_AGAINST_LIVE in FEATURE_MATRIX.md until exercised with real credentials.
"""
import httpx

from ..config import settings


class BolnaError(Exception):
    def __init__(self, code: str, status: int = 502, message: str = "", scope: str | None = None):
        super().__init__(message or code)
        self.code, self.status, self.scope = code, status, scope


class CircuitBreaker:
    """Opens after `threshold` consecutive provider failures; half-opens after `cooldown` seconds."""

    def __init__(self, threshold: int = 3, cooldown: float = 30.0, clock=None):
        import time
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock or time.monotonic
        self.failures, self.opened_at = 0, None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if self.clock() - self.opened_at >= self.cooldown:
            return True  # half-open: allow one probe
        return False

    def record(self, ok: bool) -> None:
        if ok:
            self.failures, self.opened_at = 0, None
        else:
            self.failures += 1
            if self.failures >= self.threshold:
                self.opened_at = self.clock()


BREAKER = CircuitBreaker()


class BolnaClient:
    name = "bolna"

    def __init__(self, base_url: str, api_key: str, agent_id: str, timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self.base_url, self.agent_id = base_url.rstrip("/"), agent_id
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def _request(self, method: str, path: str, **kw) -> dict:
        if not BREAKER.allow():
            raise BolnaError("provider_circuit_open", 503, "Voice provider temporarily unavailable; retry shortly")
        try:
            out = self._request_once(method, path, **kw)
        except BolnaError as e:
            if e.code in ("provider_timeout", "provider_unavailable"):
                BREAKER.record(False)
            raise
        BREAKER.record(True)
        return out

    def _request_once(self, method: str, path: str, **kw) -> dict:
        try:
            r = self._http.request(method, path, **kw)
        except httpx.TimeoutException as e:
            raise BolnaError("provider_timeout", 504, "Bolna did not respond in time") from e
        except httpx.HTTPError as e:
            raise BolnaError("provider_unavailable", 502, "Could not reach Bolna") from e
        if r.status_code in (401, 403):
            raise BolnaError("provider_auth_failed", 502, "Bolna rejected the server credentials")
        if r.status_code == 429:
            raise BolnaError("at_capacity", 503, "All voice lines are busy", scope="global")
        if r.status_code >= 500:
            raise BolnaError("provider_unavailable", 502, f"Bolna returned {r.status_code}")
        if r.status_code >= 400:
            raise BolnaError("provider_rejected", 502, f"Bolna returned {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise BolnaError("provider_bad_response", 502, "Bolna returned non-JSON") from e
        if not isinstance(data, dict):
            raise BolnaError("provider_bad_response", 502, "Unexpected response shape")
        return data

    def mint_web_session(self, user_data: dict | None = None) -> dict:
        body: dict = {"agent_id": self.agent_id}
        if user_data:
            body["user_data"] = user_data
        try:  # the SDK contract names /freeswitch-session; the API docs name /web-call/session (seen in other projects' code)
            return self._request("POST", "/web-call/freeswitch-session", json=body)
        except BolnaError as e:
            if e.code != "provider_rejected" or e.status != 502 or "404" not in str(e):
                raise
            return self._request("POST", "/web-call/session", json=body)

    def start_outbound(self, phone: str, user_data: dict | None = None) -> dict:
        body: dict = {"agent_id": self.agent_id, "recipient_phone_number": phone}
        if user_data:
            body["user_data"] = user_data
        return self._request("POST", "/call", json=body)

    def get_execution(self, execution_id: str) -> dict:
        return self._request("GET", f"/executions/{execution_id}")


def make_client() -> BolnaClient:
    if not settings.bolna_configured:
        raise BolnaError("PROVIDER_NOT_CONFIGURED", 503, "Bolna credentials are not configured")
    return BolnaClient(settings.bolna_base_url, settings.bolna_api_key, settings.bolna_agent_id,
                       settings.bolna_timeout_seconds)


# Forward-only call lifecycle. Unknown provider statuses are stored but never advance state.
STATUS_RANK = {"queued": 1, "initiated": 1, "ringing": 2, "in-progress": 3, "call-disconnected": 4,
               "completed": 5, "busy": 5, "no-answer": 5, "failed": 5, "canceled": 5, "cancelled": 5,
               "stopped": 5, "balance-low": 5, "error": 5}
