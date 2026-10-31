# Implementation evidence — RESOLVE + RECLAIM inheritance phase

Scope: inherit the functionality of RESOLVE and RECLAIM into REDEEM's single mission engine. Per-feature status lives in `FEATURE_INHERITANCE_MATRIX.md`; this file records what was built, where it came from, and how it was verified. Source repos were read as data only (via `ast`/text); no third-party code was executed.

## What was built (source → destination)

| Inherited from | Destination in REDEEM | Notes |
|---|---|---|
| RECLAIM knowledge base + scoring | `apps/api/app/reclaim/kb.py`, `data/corpus.jsonl` (built by `scripts/build_knowledge_corpus.py`) | BM25 retrieval, authority-tier evidence scoring, citation verification (only retrieved `[kb_…]` ids may be cited), provenance labels `scraped_official` vs `authored_guide` |
| RECLAIM domain profiles/router | `reclaim/profiles.py`, `data/domain_*.json` | 8 consumer-rights domains, router with anchors/providers, entity extraction |
| RECLAIM workflows / decision | `reclaim/workflows.py`, `reclaim/decision.py` | Per-domain intake, checklists, escalation ladder, drafts; ranked actions with labelled assumptions |
| RECLAIM document intelligence | `reclaim/docintel.py` | Facts → source quote/page, strength, claim mapping, duplicate/version detection; OCR is BLOCKED (no engine) |
| RECLAIM case lifecycle | `reclaim/casework.py`, `api/cases.py`, `cases` tables (migrations 0002–0006) | 17-stage persisted pipeline; approval bound to draft hash + action; guided handoff (no real filing); VERIFIED only with a supporting document |
| RESOLVE fixture apps | `resolve/web_fixtures.py` | Stateful CRM / report store / outbox on tenant loopback |
| RESOLVE browser runner | `resolve/browser.py`, `connectors/browser.py` | Fresh Chromium context per run, request allow-list, before/after DOM/ARIA/screenshot/API hashes, user-only-step (login/CAPTCHA/MFA) pause |
| RESOLVE file worker / PDF studio | `resolve/file_worker.py`, `resolve/document_studio.py`, `api/workspace.py` | Dedupe, dry-run, stale-plan guard, apply, undo; source-hash guard |
| RESOLVE command interpreter | `orchestration/utterance.py` | stop/pause/resume/change/undo/explain/what-happened |
| Task DAG, agent roles | `orchestration/taskgraph.py`, `agents.py`, table `mission_tasks` | Persisted DAG; only `executor` may dispatch |

UI: Command Center, Cases + case workspace, Mission workspace (DAG, browser panel, evidence, commands), Evidence Vault, Knowledge, Files, PDF Studio, Domains, Workflows, Connections, Voice Studio, Quality Lab, Demo, Settings, landing page.

## Verification (commands run in this session)

| Check | Result |
|---|---|
| Backend `cd apps/api && python -m pytest -q` | 195 passed (final run this session) |
| `ruff check apps/api/app` | All checks passed |
| `cd apps/web && npx tsc --noEmit` | clean |
| `npx eslint .` | 0 errors, 13 warnings |
| `npx next build` | compiled successfully |
| Playwright full suite (31 tests: older sprint specs + `inherit.spec.ts`) | first full run 27 passed / 4 failed; the 4 were specs stale against the rewritten UI (Domains tabs, Language selector duplicated in mobile/desktop nav, ambiguous "Resume" button, removed first-use panel). Specs were updated to the new UI (no assertion weakened: same behaviour checked) and the first-use panel was restored; the 4 re-ran green (4 passed) |

Failure paths covered by tests include: PROVIDER_NOT_CONFIGURED, stale approval digest, stale file plan (409), paused mission refusing execution, uncertain outcome → reconcile instead of resend, IDOR on every new resource, request outside the browser allow-list, user-only step pause, missing supporting document keeps a case unverified.

## Screens exercised (real browser, screenshots in `docs/screenshots/`)

`command-center-desktop.png`, `command-center-mobile.png`, `mission-desktop.png`, `cases-desktop.png`, `vault-desktop.png`, `knowledge-desktop.png`, `domains-desktop.png`, `quality-desktop.png` plus earlier landing/console/receipt shots.

## Persisted-state evidence

Missions, tasks, approvals, ledger events with hash-chained receipts, cases, documents, facts, drafts, browser snapshots and file-plan history are database rows under the session tenant; reload and restart-recovery tests read them back.

## Limitations (unchanged, not papered over)

No live Bolna call, no LLM, no OCR engine, no real filing/email/airline/bank, no production browser isolation (same host as API), Postgres/Docker untested, synchronous execution. Not inherited: recorded browser skills (record→compile→replay→repair), brief→PDF hero mission, devops/science/creative adapters, project store, native Windows, local STT, LLM agents/graph/vector DB/scrapers/OCR, insurance corpus. See `OPEN_BLOCKERS.md` and `MANUAL_ACTIONS_LATER.md`.

## External dependencies

Bolna credentials/numbers, an LLM key, an OCR engine, production browser sandbox, Postgres — all required for any status above `LOCALLY_TESTED`.

## Cinematic UX + encryption pass (latest)

- New single-accent cinematic theme, 3D tilt cards, canvas starfield, 3D exploded stage stack, intro (RE from the left, DEEM from the right), scroll reveals — `apps/web/components/Cinematic.tsx`, `Showcase.tsx`, `app/page.tsx`, `app/globals.css`. All motion honours `prefers-reduced-motion`.
- **Live Engine** (`/app/live`): runs a demo mission on the real engine, then replays its stored ledger events with play/pause/scrubber/speed; task DAG nodes light up as the events proving them arrive. Evidence: `docs/media/live-engine.gif|mp4`, `docs/screenshots/v2/live-*.png`. The landing "simulation loop" is illustrative and labelled so.
- **Encryption at rest** (`apps/api/app/security/vault.py`): AES-256-GCM; file bytes keyed per tenant (HKDF, tenant id as AAD), extracted text encrypted via the `EncryptedText` column type. `tests/test_encryption.py` asserts raw DB rows/blobs hold no plaintext, owner download still works, other tenant gets 404 and cannot decrypt a copied blob, master key file is 0600. Limit: server-held key, not end-to-end.
- `GET /api/v1/public/stats`: unauthenticated aggregate counters (tested to expose no tenant data).
- Verification this pass: backend **199 passed**; Playwright **35 passed** (31 earlier + 4 new in `cinematic.spec.ts`); `tsc` clean; `eslint` 0 errors; `ruff check app` clean. A first run caught a real horizontal-overflow regression on the landing page (pre-reveal off-screen translate); fixed with `main { overflow-x: clip }` and re-verified.
- README regenerated with embedded screenshots/GIFs and 3D SVGs (`scripts/build_readme_assets.py`; the Bolna/YC tiles are text marks, not official logos). Reusable prompt: `docs/CINEMATIC_UX_PROMPT.md`.
- Not done / honest limits: no WebGL/three.js scene (CSS 3D + canvas only), so this is not Unreal/PS5-class rendering; the GIF/MP4 are assembled from Playwright screenshots, not a screen recording; Postgres and Docker still untested.

## Database pass
Postgres 16 (throwaway server via `scripts/dev_postgres.sh`, UTF8): `alembic upgrade head` OK, `alembic check` no drift, full backend suite **199 passed** (+1 health-dialect test). Found and documented: a SQL_ASCII database makes psycopg return bytes and breaks SQLAlchemy 2.1 startup, so the DB must be UTF8 (compose now passes `--encoding=UTF8`). Added `psycopg[binary]` to requirements, compose healthcheck + data volume, `dialect` in `/health`. Not verified: the Docker build/compose run itself.
