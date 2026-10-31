# Static parts to make dynamic

| Item | File | What is static | To make dynamic |
|---|---|---|---|
| Scenario overview page | apps/web/app/app/computer/scenarios/page.tsx | `SCENARIOS` array hardcoded | Add `GET /api/v1/computer/scenarios` returning scenario list + last run status from `computer_tasks` |
| File Explorer + PDF scenario | (none yet) | Only listed on the scenarios page | Add `do_files` intent in `apps/api/app/computer/agent.py` using launch_application("explorer"), OCR grounding, key combos; test on Windows CI |
| Consumer case via portal | (none yet) | Only listed | Add intent that creates a Case, opens a demo portal page (like `demo_crm.py`), fills it, uses approval digest for Submit |
| Execution report | docs/REDEEM_REAL_COMPUTER_EXECUTION_REPORT.md | Written by hand | Regenerate counts from pytest/CI output |
| Live view | apps/web/app/app/computer/page.tsx | Polls frames ~1/s (real, not static) | Optional: WebRTC video |
| Vision planner | apps/api/app/api/computer.py `status()` | Reports PROVIDER_NOT_CONFIGURED | Add model adapter returning structured action proposals |

Already dynamic and tested: pairing, devices, sessions, cloud computer, CRM task, pause/takeover/stop, approvals, Bolna computer tools, Live Computer page.
