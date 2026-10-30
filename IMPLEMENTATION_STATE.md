# Implementation state
- Branch: claude/peaceful-turing-xnfcuc
- Done: kernel, auth, both flagship missions on fixtures, recovery, Bolna adapter (mock-tested), web UI. Not done: G8–G11 mostly.
- Verify: `cd apps/api && python -m pytest -q` (58 pass); `cd apps/web && npx tsc --noEmit && npx next build && PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` (6 pass).
- Credentials: none. Missing BOLNA_API_KEY, BOLNA_AGENT_ID, BOLNA_WEBHOOK_SECRET.
- Known UI nit: hotel action amount shows "—"; ledger may briefly show empty until SSE connects.
- Next: real Bolna web call + webhook read-back; Alembic; benchmark runner; Docker; diagrams.
