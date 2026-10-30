# Implementation state
- Branch: claude/peaceful-turing-xnfcuc
- Done: kernel, auth, both flagship missions on fixtures, recovery, Bolna adapter (mock-tested), web UI. Not done: G8–G11 mostly.
- Verify: `cd apps/api && python -m pytest -q` (60 pass); `cd apps/web && npx tsc --noEmit && npx next build && PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` (6 pass).
- Credentials: none. Missing BOLNA_API_KEY, BOLNA_AGENT_ID, BOLNA_WEBHOOK_SECRET.
- Sprint 2 so far: benchmark + methodology, Alembic migration, Docker files (untested), ledger preload and hotel "No charge" UI fixes.
- Sprint 2 prompt was truncated at item 12; deployment scope unspecified.
- Next: real Bolna web call; calendar connector for the cross-domain mission; ablations; Postgres run; web lint; Bolna tool-calling.
