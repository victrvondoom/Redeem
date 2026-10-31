# Static parts to make dynamic

Status is only "Done" when there is code AND a test that exercises it. Status of items not run is stated as "Not run".

| Item | Where | Status | Evidence |
|---|---|---|---|
| Scenario overview page | `apps/web/app/app/computer/scenarios/page.tsx` | **Done (code)**; page rendered by browser: Not run | Static array removed. Page reads `GET /api/v1/computer/scenarios`; filters, detail, history and run call the real API. `tsc` result in the execution report. |
| Scenario catalog + last-run status | `app/computer/scenarios.py`, `app/api/computer.py`, migration `0012` | **Done** | `tests/test_scenarios.py`: DB-backed built-ins, never-run = `null`, last run derived from `computer_tasks` (all status transitions), tenant isolation, CRUD + versions + enable/disable, typed-step validation (no code), unrunnable scenarios return 501. |
| Consumer case via portal | `app/computer/portal.py`, `agent.do_portal_case` | **Done on Linux (Xvfb + Chromium + real bridge)**; Windows: Not run | `tests/test_portal_live.py`. Portal is a REDEEM-owned first-party target, never an external filing. |
| Exact-parameter approval for portal | `agent.do_portal_case` | **Done** | Approval digest covers a label that embeds the payload digest; different payload => different digest (live test). |
| File Explorer + PDF scenario | catalog entry only | **NOT built** | Catalog marks it not runnable (`501 not_implemented`). Needs bridge file operations (list/stat/hash/move inside allowed roots) and an interactive Windows run. See "Remaining" below. |
| Vision planner | `app/computer/vision.py`, `/api/v1/computer/vision`, `/sessions/{id}/vision/propose` | **Adapter written; live provider test: Not run** (no credentials in this environment) | Status endpoint reports `PROVIDER_NOT_CONFIGURED` honestly. Unit tests only cover unconfigured state. Proposal validation/grounding code exists but has not been exercised against a real model. |
| Execution report | `docs/REDEEM_REAL_COMPUTER_EXECUTION_REPORT.md` | Partly dynamic | See the report; counts come from pytest output captured by a script run, not typed by hand. |
| Live view | `apps/web/app/app/computer/page.tsx` | Unchanged | Frames ~1/s (real, not static). |

## ProofGraph items (domains, remedies, timeline, sources, extraction, counter, artifacts, brief, api, panels)
**Not started.** The ProofGraph commit `90dd975` / branch `agent/redeem-proofgraph` is not present in this repository (not on origin, unknown object). Source files were not recreated from descriptions.

## Remaining
- Bridge file operations + allowed-root configuration + Windows interactive test for the File Explorer/PDF scenario.
- Windows CI (`windows-bridge`): Not run (no push to a Windows runner yet).
- Playwright spec for `/app/computer/scenarios`: Not written.
- Vision: connection test with real credentials; integration of `propose` into the agent loop.
