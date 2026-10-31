# REDEEM real computer execution report

## Clicky inspection
farzaa/clicky (MIT) is a macOS menu-bar app: ScreenCaptureKit capture, push-to-talk, Claude replies with `[POINT:x,y:label:screenN]` and an overlay cursor points there. It never injects mouse or keyboard input. REDEEM adapted the concepts (per-monitor capture metadata, pixel-to-screen mapping, visible pointer overlay, keys kept server-side). No code was copied.

## Built
- Bridge `apps/bridge`: Windows (SendInput, EnumWindows, UI Automation, GDI capture) and X11 (XTEST, mss). Outbound WebSocket only, token rotated each connect, local pause/takeover/emergency stop, Tk window + click-through orange pointer overlay (Windows).
- Server `apps/api/app/computer`: pairing (one-time 10-min codes), sessions, action pipeline (schema, risk, approval digest, stale-target check, persist-before-act, UNCERTAIN on timeout), OCR grounding, closed-loop agent, demo CRM, cloud computer (Xvfb + Chromium + bridge), restart recovery.
- Bolna tools: computer_task / computer_status / computer_control / computer_approve.
- Web: /app/computer (live frames, timeline, approvals, takeover by clicking the frame), /app/computer/scenarios (static).

## Evidence
- `apps/api/tests/test_computer.py`: 9 passed on real Xvfb displays (pairing+revoke, CRM end to end, pause/takeover/replan, emergency stop, bound approval, stale target, Bolna tools).
- `apps/bridge/tests/test_x11.py`: passed. `test_windows.py`: runs in `.github/workflows/windows-bridge.yml` (result not yet observed).
- Final CRM frame: docs/media/computer-crm-final.png.

## Limits / missing authorizations
No live Bolna call (no BOLNA_API_KEY/AGENT_ID/WEBHOOK_SECRET). No vision/LLM model (rule-based OCR planner). Live view is ~1 fps frames, not WebRTC. Cloud isolation is process-level, not VM. File Explorer/PDF and case-portal scenarios not built (see docs/STATIC_TODO.md).

## Dynamic scenarios pass (branch agent/redeem-computer-dynamic)
Numbers below are copied from the actual runs of this pass (pytest output), not estimated.

| Check | Result |
|---|---|
| `python -m pytest -q` (apps/api, Linux, Xvfb available) | 272 passed, 1 skipped, **1 failed** (476.95 s) |
| The failure | `tests/test_sprint4.py::test_exported_agent_tools_match_the_endpoints_and_accept_bolna_flat_bodies`: pre-existing at base commit d09971c (it lists 8 Bolna tools; d09971c added 4 `computer_*` tools). Not modified in this pass. |
| `ruff check .` | passed |
| `tests/test_scenarios.py` (headless API + DB) | 14 passed |
| `tests/test_portal_live.py::test_portal_scenario_fills_form_waits_for_exact_approval_then_submits` (real Xvfb + Chromium + bridge, Linux) | passed in an earlier targeted run (52.98 s); also part of the full run above |
| `alembic upgrade head` + `alembic check` on a fresh DB | "No new upgrade operations detected" |
| `npx tsc --noEmit` (apps/web) | passed |
| `npx eslint app/app/computer` | 0 errors, 2 warnings (set-state-in-effect) |
| `next build`, Playwright (all specs), Windows `windows-bridge` CI | **Not run** |
| File Explorer + PDF scenario | **Not built** (catalog says not runnable; API returns 501) |
| Vision provider live test | **Not run** (no credentials; status endpoint reports PROVIDER_NOT_CONFIGURED) |
| Windows interactive UI automation | **Not run** |
| ProofGraph dynamic configuration | **Not started** (ProofGraph commit 90dd975 is not in this repository) |
