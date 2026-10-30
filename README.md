# REDEEM — Speak your need. We take the lead.
Voice-first agent platform: understands a problem, prepares exact actions, asks approval, executes via connectors, then **independently verifies** the result and issues a receipt. Built for the Bolna × YC Symphony Buildathon 2026 (not endorsed by Bolna or Y Combinator).

## What works today
- FastAPI kernel: argon2 auth, HttpOnly cookie + CSRF, tenant isolation, typed mission state machine, digest-bound approvals, append-only ledger, reconcile-not-resend, restart recovery, hash-chained receipts, SSE stream.
- Two flagship missions against **stateful local fixtures** (no real airline or shop): flight-refund recovery and shop reservation.
- Bolna adapter: session minting (key never reaches the browser), consent gate, call ledger, webhook with read-back. Tested with a mock transport only — **no live call has been made**; without credentials the UI shows `PROVIDER_NOT_CONFIGURED`.
- Next.js UI: landing with working composer, console, mission workspace, voice studio, domains + payment-safety scan, connections, evidence vault, history, quality lab, settings.
- Sprint 3: calendar + CRM + case-desk fixtures (cross-domain mission), safety engine, citation validator, SSRF guard, workflow library, Bolna tool endpoints, benchmark with ablations, Alembic migrations, Docker files (unbuilt), ESLint.
- Not built / unverified: live Bolna calls, Postgres run, Docker build, real regulatory sources, isolated cloud browser, task-graph compiler, billing/developer domains (see FEATURE_MATRIX.md, docs/OPEN_BLOCKERS.md, docs/MANUAL_ACTIONS_LATER.md).

## Run
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r apps/api/requirements.txt
cd apps/api && python -m pytest -q   # 90 tests
alembic upgrade head   # optional; the app also creates tables on start
uvicorn app.main:app --port 8000
```
```bash
cd apps/web && npm install && npm run build && npx next start -p 3000
```
Open http://localhost:3000. Provider variables are in `.env.example`.

## Security boundaries
Tenant from session only; CSRF on mutations; external text (documents, transcripts) is data and cannot approve or run actions; outbound calls need a flag, an allow-listed number and consent; fixture fault injection is switchable off.

## Limitations
Synchronous execution, process-local rate limiter, SQLite-tested only, unreviewed translations, no performance claims.
