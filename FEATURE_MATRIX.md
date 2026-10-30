# Feature matrix (truthful)
| Feature | Status | Evidence |
|---|---|---|
| Auth, sessions, CSRF, rate limit, tenant isolation | LOCALLY_TESTED | apps/api/tests/test_auth_tenancy.py |
| Mission state machine, digest approvals, ledger, receipts | LOCALLY_TESTED | tests/test_flight_mission.py |
| Flight-refund mission (fixture) | END_TO_END_VERIFIED (fixture only) | pytest + Playwright |
| Retail reservation + CRM stage (fixture) | END_TO_END_VERIFIED (fixture only) | pytest + Playwright |
| Intent correction, approval invalidation, stale-exec abort | LOCALLY_TESTED | pytest |
| Ack-loss reconcile, silent-drop detection, restart recovery | LOCALLY_TESTED | pytest + Playwright |
| Bolna session mint, webhook, call ledger | LOCALLY_TESTED (mock transport) | tests/test_voice_bolna.py; no live call made |
| Bolna outbound + execution read-back | IMPLEMENTING (contract unverified) | mock only |
| Multilingual UI en/hi/hinglish/ta/te | LOCALLY_TESTED; no native review; detail screens mostly English | Playwright |
| Live voice quality per language | BLOCKED (needs Bolna credentials) | — |
| Payment-safety scanner | LOCALLY_TESTED (heuristic) | tests |
| Legal citations, PDF parsing, workflow builder, benchmarks, Alembic, Postgres, worker, Docker, other domains | IDEA/SPECIFIED — not built | — |
| Deployment | not done | — |
