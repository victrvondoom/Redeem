# End-to-end evidence (this session)

| Check | Command | Result |
|---|---|---|
| Backend | `cd apps/api && python -m pytest -q` | 240 passed, 1 skipped (live Google test, needs credentials) |
| Lint | `ruff check apps/api` (app, tests, migrations) | clean |
| Types and build | `cd apps/web && npx tsc --noEmit && npx next build` | clean, builds |
| ESLint | `npx eslint .` | 0 errors, 19 warnings (React-compiler state-in-effect notices) |
| Browser E2E | `npx playwright test` (real Chromium, API on :8000, web on :3000) | 43 passed |
| Migrations | `alembic upgrade head && alembic check` | no drift (0001 to 0009) |
| Design floor | `node scripts/ui_floor_check.mjs` | 0 FAIL |
| PostgreSQL 16 | full suite earlier in the project (199 at the time) | passed; **not re-run for the 40 tests added since** |

## New this pass, with evidence
- **OCR**: `tests/test_ocr.py` (4) and `apps/web/tests/live.spec.ts`: a PNG photo and a scanned PDF are read by RapidOCR; a blank image reports `OCR_NO_TEXT_FOUND`; the user can correct the text and facts are recomputed while the original bytes stay unchanged. Screenshot: `docs/screenshots/v6/ocr-review.png`.
- **Brief to PDF**: `tests/test_brief.py` (2) and the browser test: structure extracted from the user's own words, edited, rendered to a PDF whose text is read back with pypdf, stored encrypted with provenance. Screenshot: `docs/screenshots/v6/brief-to-pdf.png`.
- **Google adapter, Connections Center**: `tests/test_integrations.py` (11 plus 1 skipped), `live.spec.ts`. Screenshot: `docs/screenshots/v6/connections-live-providers.png` shows the real unconfigured state with the missing variable names.
- **Demo separation**: in `REDEEM_ENV=production` no simulated bookings, shop or CRM are seeded and demo runs return 403.

## Not evidenced
No live Bolna call, no live Google call, no recorded product video, no browser-skills workflow, no LLM, no speech-to-text. Memory continuity, history, graph, encryption and rotation are evidenced in the earlier sections of `docs/IMPLEMENTATION_EVIDENCE.md`.

## Skills, projects and logos pass (2026-10-31)
| Command | Result |
|---|---|
| `cd apps/api && python -m pytest -q` (Python 3.12, local Chromium) | 245 passed, 1 skipped (live Google test: no credentials) |
| `ruff check app tests` | clean |
| `npx tsc --noEmit && npx next build` | green |
| `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` | 46 passed |

Evidence for the new features:
- `test_record_replay_persists_real_state_and_frames`: a skill is recorded in Chromium, replayed with new parameters, and both tasks are read back from the CRM app's own `/api/tasks` (not the UI toast); each step's PNG is served; another tenant gets 404 on the skill, run and screenshot.
- `test_failed_replay_after_click_is_uncertain_and_not_retried`: unknown contact, run FAILED at step 6, `uncertain=true`, nothing written.
- `test_live_run_pause_resume_stop`: background run paused (no step progress for 1 s), then stopped (status STOPPED, fewer than 6 steps); control on a finished run is refused (409).
- `test_project_store_crud_and_idor`: CRUD, search, duplicate refusal, cross-tenant 404s, export contains only the caller's projects.
- E2E `skills_projects.spec.ts`: the intro shows both official logo images; the Browser skills page shows the run live (observed mid-run: "running step 4 of 6" with the step-4 screenshot) and 6 frames at the end; the skill survives reload with "2 runs"; project lifecycle.
