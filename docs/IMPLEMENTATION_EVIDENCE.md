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
