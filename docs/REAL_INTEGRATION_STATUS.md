# Real integration status

Checked in this session. Configuration is reported by variable name only; no secret values were read or printed.

| Provider | Authorization needed | Variables | Configured here | Connection test | Operations tested | Independently verified live | Missing manual step |
|---|---|---|---|---|---|---|---|
| Bolna voice | API key, agent id, webhook secret | `BOLNA_API_KEY`, `BOLNA_AGENT_ID`, `BOLNA_WEBHOOK_SECRET` | No | Not run (no key) | Web session, outbound call, execution read-back, webhook with read-back, agent tools `save_answer`/`recall` against a mock transport (contract tests) | **No.** No live call has ever been made | Create a Bolna agent and key, set the three variables, make one call. Bolna's public docs were not reachable from the build sandbox, so the request shapes in `app/voice/bolna.py` are unverified against the live API |
| Google Calendar and Gmail | OAuth 2.0 client (authorization code, offline access) | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` | No | Not run | OAuth state/exchange/refresh/revoke, idempotent calendar insert, Gmail send, read-back verification, lost-reply reconcile, scope and tenant isolation: 11 tests against an **in-process fake of Google's documented endpoints** | **No.** A live test (`test_live_google_refresh_and_userinfo`) exists and is skipped until `GOOGLE_TEST_REFRESH_TOKEN` is set | Create the OAuth client in Google Cloud Console, add the redirect URI, set the variables, press Connect Google in Connections |
| Y Combinator, WeMakeDevs, Symphony | none | none | n/a | n/a | n/a | n/a | Branding only. Y Combinator logo and the Bolna image were supplied by the project owner |
| LLM provider | API key | none defined | No key present | n/a | n/a | n/a | No LLM is wired anywhere. A key and an adapter are both missing |
| Speech to text (local) | model download | none | n/a | n/a | n/a | n/a | Needs a model download that the sandbox cannot make |
| Airline, bank, insurer, telecom, retailer, government portals | each provider's own program or credentials | none | n/a | n/a | n/a | n/a | No adapters exist. These workflows prepare documents and hand off; they never file, send or book |

Other credentials in this environment (cloud keys) are unrelated to REDEEM and were deliberately not used.

## Where real behaviour does exist without credentials
Real OCR (RapidOCR), real PDF generation, real Chromium on loopback fixture apps, real AES-256-GCM encryption, real PostgreSQL 16 (verified locally), real persisted memory, history and graph.
