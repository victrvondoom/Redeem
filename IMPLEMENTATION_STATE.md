# Implementation state
- Branch: claude/peaceful-turing-xnfcuc
- Done: kernel, auth, both flagship missions on fixtures, recovery, Bolna adapter (mock-tested), web UI. Not done: G8–G11 mostly.
- Verify: `cd apps/api && python -m pytest -q` (121 pass); `cd apps/web && npx tsc --noEmit && npx next build && PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` (20 pass).
- Credentials: none. Missing BOLNA_API_KEY, BOLNA_AGENT_ID, BOLNA_WEBHOOK_SECRET.
- Sprint 2 so far: benchmark + methodology, Alembic migration, Docker files (untested), ledger preload and hotel "No charge" UI fixes.
- Sprint 2 prompt was truncated at item 12; deployment scope unspecified.
- Next: real Bolna web call; calendar connector for the cross-domain mission; ablations; Postgres run; web lint; Bolna tool-calling.

## Sprint 3
See docs/EXECUTION_LOG.md, OPEN_BLOCKERS.md, VERIFICATION_EVIDENCE.md, MANUAL_ACTIONS_LATER.md. Next exact action: implement the task-graph compiler (dependency-aware scheduling) in apps/api/app/orchestration/, then add remaining ablations (entity binding, temporal guard, ledger) to evals/runners/benchmark.py.

## Sprint 4
Last verified: 121 pytest, 20 Playwright, tsc/eslint/build green. Next exact action: with Bolna credentials run M1/M2/M13 (create agent from `python -m app.voice.agent_config`), place one live call, and only then change the bolna manifest condition from UNCONFIGURED. Without credentials: durable worker/outbox (apps/api/app/orchestration/), CallGrade-style intervals in Quality Lab, collapse the ledger on completed missions.

## RESOLVE + RECLAIM inheritance phase (latest)
- Backend: 195 passed. Playwright: 31 tests (older sprint specs updated to the rewritten UI + new `inherit.spec.ts`), all green.
- See `docs/FEATURE_INHERITANCE_MATRIX.md` (per-feature status) and `docs/IMPLEMENTATION_EVIDENCE.md` (evidence, limits).
- Not inherited: recorded browser skills, brief→PDF mission, devops/science/creative adapters, project store, local STT, OCR/LLM.

## Cinematic UX + encryption (latest)
Backend 199 passed; Playwright 35 passed. New: Live Engine page, cinematic landing/theme, AES-256-GCM document encryption at rest, public aggregate stats, README with embedded media. See docs/IMPLEMENTATION_EVIDENCE.md.

## 250-task pass (latest)
Backend 217 passed, E2E 38. Added: orange/graphite theme, REDEEM intro (Bolna + Wispr Flow cubes; official logos blocked), envelope encryption with rotation, persistent encrypted memory + Memory Center, Privacy Center, Bolna save_answer/recall tools, README rewrite + generated feature table + CI. See docs/TASKS_250_STATUS.md for what is NOT done.
