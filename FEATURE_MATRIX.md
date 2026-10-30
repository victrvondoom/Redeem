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
| Seeded policy benchmark (3 policies × 5 scenarios × 30 trials, raw JSON) | LOCALLY_TESTED (fixture only; REDEEM 150/150 on its own designed scenarios, so not evidence of general reliability) | evals/runners/benchmark.py, evals/METHODOLOGY.md, tests/test_benchmark.py |
| Alembic initial migration (SQLite) | LOCALLY_TESTED (drift check) | tests/test_migrations.py |
| Dockerfiles + compose (Postgres) | IMPLEMENTING — untested, no Docker daemon in sandbox | — |
| Cross-domain mission (flight + hotel + calendar) | PARTIAL: flight + hotel in one mission; calendar not built | — |
| Legal citations, PDF parsing, workflow builder, benchmark ablations, background worker, tool/function calling, post-call analysis, other domains, web lint, cloud-browser isolation | IDEA/SPECIFIED — not built | — |
| Deployment | not done | — |
