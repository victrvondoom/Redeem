"""Connector manifests. `condition` is never LIVE_VERIFIED unless a live exercise has been recorded (none has)."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Manifest:
    provider: str
    kind: str                      # fixture | api_key | oauth | http | browser
    auth: str
    scopes: list[str]
    capabilities: list[str]
    rate_limit: str
    retry: str
    idempotency: str
    verification: str
    revocable: bool
    condition: str                 # UNCONFIGURED | FIXTURE_VERIFIED | LIVE_VERIFIED
    notes: str = ""
    extra: dict = field(default_factory=dict)


_FX = dict(kind="fixture", auth="none (in-process stateful fixture)", rate_limit="none", revocable=True, condition="FIXTURE_VERIFIED")
MANIFESTS = [
    Manifest("booking_fixture", scopes=["booking:read", "booking:request"], capabilities=["refund_request", "hotel_change_request"],
             retry="no automatic resend; reconcile by lookup", idempotency="idempotency key honoured", verification="read request rows + refund status", **_FX),
    Manifest("calendar_fixture", scopes=["calendar:read", "calendar:write"], capabilities=["calendar_update"], retry="state-based, naturally idempotent",
             idempotency="state-based", verification="read event status", **_FX),
    Manifest("retail_fixture", scopes=["catalogue:read", "stock:reserve", "crm:write"], capabilities=["reserve_stock"], retry="no automatic resend",
             idempotency="idempotency key + atomic decrement", verification="reservation row + stock delta", **_FX),
    Manifest("crm_fixture", scopes=["crm:read", "crm:write"], capabilities=["crm_followup"], retry="stale record → re-read and re-approve",
             idempotency="optimistic version check", verification="query lead stage/date", **_FX),
    Manifest("casedesk_fixture", scopes=["case:write"], capabilities=["prepare_case"], retry="idempotent create", idempotency="idempotency key",
             verification="read case row", notes="Internal case record only; nothing filed externally.", **_FX),
    Manifest("comms_fixture", scopes=["message:draft"], capabilities=["notify_contact"], retry="idempotent create", idempotency="idempotency key",
             verification="read draft row", notes="Drafts only; nothing is sent.", **_FX),
    Manifest("bolna", kind="api_key", auth="server-side bearer API key", scopes=["voice:web_call", "voice:outbound"],
             capabilities=["web_call_session", "outbound_call", "execution_readback", "function_tools", "webhook"], rate_limit="provider-side; circuit breaker local",
             retry="reads only; bounded", idempotency="n/a (calls are not retried)", verification="execution read-back", revocable=False, condition="UNCONFIGURED",
             notes="Live status requires BOLNA_API_KEY + BOLNA_AGENT_ID and a recorded live call."),
    Manifest("generic_http", kind="http", auth="per-connector header (not configured)", scopes=[], capabilities=["http_request"], rate_limit="n/a", retry="reads only",
             idempotency="caller-supplied key", verification="caller-defined read-back", revocable=True, condition="UNCONFIGURED",
             notes="Requests must pass the SSRF guard. No endpoints configured."),
    Manifest("google_calendar", kind="oauth", auth="OAuth 2.0 (client not configured)", scopes=["calendar.events"], capabilities=["calendar_update"], rate_limit="provider quota",
             retry="reads only", idempotency="event id", verification="events.get read-back", revocable=True, condition="UNCONFIGURED"),
    Manifest("email_provider", kind="api_key", auth="API key (not configured)", scopes=["message:send"], capabilities=["email_send"], rate_limit="provider quota",
             retry="none", idempotency="message id", verification="provider delivery receipt", revocable=True, condition="UNCONFIGURED"),
    Manifest("cloud_browser", kind="browser", auth="isolated runtime (not configured)", scopes=["browser:navigate"], capabilities=["browse"], rate_limit="n/a", retry="none",
             idempotency="n/a", verification="screenshot + DOM read-back", revocable=True, condition="UNCONFIGURED", notes="BLOCKED without an isolated runtime."),
]


def manifests() -> list[dict]:
    return [asdict(m) for m in MANIFESTS]
