# Manual actions (deferred — nothing below blocks other work)
| ID | External service | Manual action | Why necessary | Code already completed | Verification command | Priority |
|---|---|---|---|---|---|---|
| M1 | Bolna | Create API key + agent; set `BOLNA_API_KEY`, `BOLNA_AGENT_ID` | Needed for any live call | Session mint, consent, call ledger, webhook, tool endpoints (mock-tested) | `curl -b cookies localhost:3000/api/v1/voice/status` → `READY`; then Voice Studio call | P0 |
| M2 | Bolna | In the agent config add function tools pointing at `/api/v1/voice/tools/{search_catalogue,lookup_booking,start_mission}?token=<secret>` and webhook `/api/v1/webhooks/bolna?token=<secret>`; set `BOLNA_WEBHOOK_SECRET` | Lets the agent call REDEEM mid-call | Endpoints + tests | place a call, check Quality Lab live section | P0 |
| M3 | Bolna docs | Confirm `POST /call` and `GET /executions/{id}` against docs.bolna.ai (unreachable from build sandbox) | Those two contracts are unverified | Adapter + mock contract tests | live outbound call to an approved number | P1 |
| M4 | Telephony | Approve a test phone number you own; set `REDEEM_ALLOW_OUTBOUND_CALLS=true`, `REDEEM_OUTBOUND_TEST_NUMBERS` | Outbound is allow-list gated | Gate + tests | `POST /api/v1/voice/calls/outbound` | P1 |
| M5 | Postgres | Run migrations on a real Postgres and run pytest with `REDEEM_DATABASE_URL=postgresql+psycopg://…` | Postgres path never executed (I started a local server once and stopped it when you interrupted) | Alembic 0001/0002, compose file | `alembic upgrade head && pytest` | P1 |
| M6 | Docker host | Run `docker compose up --build` | No Docker daemon in sandbox; compose file validated by `docker compose config` only | Dockerfiles + compose | `docker compose up --build` then open :3000 | P1 |
| M7 | Hosting/DNS | Choose host, set `REDEEM_COOKIE_SECURE=true`, domain, `REDEEM_ALLOW_FAULT_INJECTION=false` | Deployment is an account action | Env-driven config | `/api/v1/health` on the domain | P1 |
| M8 | LLM provider | Supply a key if you want model-based reasoning (not wired; routing is rule-based) | Optional | Rule-based router | n/a | P2 |
| M9 | Official sources | Provide/approve official regulatory documents to ingest into `reg_sources` | Fixture sources only; no real law is cited | RegSource table, citation validator | `GET /api/v1/sources` | P1 |
| M10 | Isolated browser runtime | Provide an isolated browser service and set `REDEEM_ISOLATED_BROWSER_URL` | Cloud browser is BLOCKED by design without isolation | SSRF guard, gate | `GET /api/v1/browser/status` | P2 |
| M11 | Native reviewers | Review hi/ta/te/Hinglish copy in `apps/web/lib/messages.ts` | Drafts are unreviewed | i18n resources | visual check per language | P1 |
| M12 | Hackathon | Record demo video; submit application (Oct 31, 2026 per organiser page — re-check) | Human submission | Demo script in docs/demo | — | P0 |
