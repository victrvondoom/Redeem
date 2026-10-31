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

## Context/graph/history + theme pass (latest)
Backend 222, E2E 40. New: conversation_turns (0008), /timeline, /context, /graph, History timeline tab, Memory Graph page, Conversation context panel, black+green+orange theme, Gloock pixel display font. README now carries the Buildathon banner and an honest "many features do not work" statement.

## UI polish pass (latest)
Hallmark rules applied as data (skill scripts not executed); `node scripts/ui_floor_check.mjs` = 0 FAIL against the running app. See docs/DESIGN_AUDIT.md. E2E 40 passed.

## Functional completion pass (latest)
Backend 240 (+1 skipped live test), E2E 43. New: real OCR (RapidOCR) with review, brief-to-PDF, Google OAuth/Calendar/Gmail adapter with approvals and reconcile-not-resend (contract-verified, credential-blocked), Connections Center live providers, demo fixtures off in production, migration 0009. See docs/FINAL_FUNCTIONAL_COMPLETION_REPORT.md and docs/REAL_INTEGRATION_STATUS.md.

## Skills, projects, logos pass (latest)
Backend 245 passed, 1 skipped (live Google test, no credentials); E2E 46 passed; ruff, tsc, eslint, next build green. New: recorded browser skills with live pause/resume/stop (`resolve/skills.py`, `/app/skills`), Project Store (`/app/projects`), migration 0010, official Bolna and Wispr Flow logos, `browser_available()` now detects Playwright-managed Chromium (CI). No provider credentials were present in this environment. Next: DevOps/Science/Creative adapters; reconcile RUNNING skill runs at startup.
