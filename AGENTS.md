# AGENTS.md — working on REDEEM
## Rules (unchanged, non-negotiable)
1. Read IMPLEMENTATION_STATE.md first; run its verification commands before new work.
2. Done = validated input → authz → execution → real state change → independent verification → durable storage → UI shows it → failure paths tested.
3. Never upgrade a status in FEATURE_MATRIX.md / docs/FEATURE_INHERITANCE_MATRIX.md without evidence. Never simulate a live provider; show PROVIDER_NOT_CONFIGURED.
4. Tenant identity comes from the session only. Filter every query by tenant_id. Add an IDOR test for every new resource.
5. Never resend a non-idempotent action after an uncertain outcome: look it up read-only, else human review.
6. Never weaken or delete a failing test. No secrets in git. Do not execute code from cloned third-party repos; read them as data.
7. No invented metrics, testimonials, citations or legal claims. Every estimate that is a heuristic is labelled an assumption.

## Architecture (what actually exists)
One mission engine (`apps/api/app/orchestration/engine.py`) drives every domain. Connectors (`app/connectors/*`) expose `version_hash / snapshot / lookup / submit / verify`; the engine owns approvals (digest-bound), the append-only ledger, reconcile-not-resend, restart recovery, pause/resume/reject/escalate, and the persisted task DAG (`taskgraph.py`, table `mission_tasks`). Agent roles are least-privilege capability sets (`agents.py`); only `executor` may dispatch.
- **Missions** (scenarios): `flight_recovery` (refund+hotel+calendar+family draft+travel case), `retail_reservation`, `crm_followup`, `case_preparation` (drives a Case), `browser_followup` (real Chromium on simulated apps).
- **RECLAIM-inherited** (`app/reclaim/`): `kb.py` (BM25 + evidence scoring + citation verification), `profiles.py` (8 domain profiles, router, entities, relevance), `workflows.py` (per-domain issues/checklists/escalation/drafts), `decision.py`, `docintel.py`, `casework.py` (17-stage persisted case lifecycle). Data in `reclaim/data/` (built by `scripts/build_knowledge_corpus.py`).
- **RESOLVE-inherited** (`app/resolve/`): `web_fixtures.py` (simulated CRM/report store/outbox), `browser.py` (Playwright runner, allow-list, snapshots, user-only-step detection), `file_worker.py` and `document_studio.py` (ported verbatim), wrapped by `api/workspace.py`.
- **Memory + crypto** (`app/memory/`, `app/security/vault.py`): `extract.py` (rule-based spoken-answer -> field mapper, clarification on ambiguity), `service.py` (encrypted `memory_items`, confirm/correct/delete, relevance, expiry, transcript ingest); vault = envelope AES-256-GCM (`encryption_keys` table, KEK from `REDEEM_MASTER_KEY`, key ids/versions, rotation, fail-closed in production). Only CONFIRMED memory feeds missions. Bolna tools `save_answer`/`recall` need the user's `memory_capture` consent.
- API routers: `auth, missions, ops (control/evidence/connectors/demo/analytics/overview/quality runs/browser), cases, voice, workspace, misc`. Migrations: `apps/api/migrations` (0001–0007, `alembic check` is a test).
- Web (`apps/web`): Next.js app router; Command Center, Cases + case workspace, Mission workspace (DAG, browser sessions, evidence, commands), Evidence Vault, Knowledge, Files, PDF Studio, Domains, Workflows, Connections, Voice Studio, Quality Lab, Demo, Settings, Live Engine (`/app/live`), Memory Center, Privacy Center. Cinematic intro + 3D components in `components/Cinematic.tsx`/`Showcase.tsx`; theme = warm graphite + ONE orange (`--accent`). Partner logos live in `public/brand/` (never redraw them). README feature table is generated: edit `registry/features.json`, run `python scripts/sync_readme.py`. Honest 250-task accounting: `docs/TASKS_250_STATUS.md`.

## Commands
```bash
. .venv/bin/activate && cd apps/api && python -m pytest -q         # backend (≈3 min)
ruff check app
cd apps/web && npx tsc --noEmit && npx eslint . && npx next build
PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test      # browser E2E (starts API on :8000 and web on :3000)
python evals/runners/benchmark.py --n 30 --seed 7                   # benchmark → evals/reports/benchmark_results.json
python scripts/build_knowledge_corpus.py /path/to/RECLAIM           # rebuild the corpus (reads data only)
```
## Honest limits (do not paper over)
No live Bolna call, no LLM, no OCR engine, no real filing/email/airline/bank, no isolated production browser, Docker build untested (Postgres 16 verified locally), execution synchronous. See docs/OPEN_BLOCKERS.md and docs/MANUAL_ACTIONS_LATER.md.
