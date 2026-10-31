# Handoff: computer-use work (branch claude/zen-pasteur-cwfkgi)

## Done and verified (Linux, real Xvfb display + Chromium + bridge process)
- `apps/bridge/`: REDEEM Computer Bridge (Windows SendInput/EnumWindows/UIA backend; X11 XTEST backend), protocol, local pause/takeover/stop, outbound WebSocket, token rotation, revoke.
- `apps/api/app/computer/`: hub, pipeline (approval digest, stale-target check, UNCERTAIN on timeout), OCR grounding, agent loop, demo CRM, cloud computer, restart recovery. Router `app/api/computer.py`. Migration 0011.
- Bolna tools: `computer_task`, `computer_status`, `computer_control`, `computer_approve`.
- Tests: `apps/api/tests/test_computer.py` (9 passed), `apps/bridge/tests/test_x11.py` (passed). Evidence frame: `docs/media/computer-crm-final.png`.
- Web: `/app/computer` Live Computer page (tsc clean, 1 lint warning).

## Not done yet (in order)
1. Run full regression: `cd apps/api && python -m pytest -q`; `cd apps/web && npx tsc --noEmit && npx eslint . && npx next build && npx playwright test`.
2. Add a Playwright spec for `/app/computer` (start cloud computer, run CRM task, see summary).
3. Push, open draft PR, check `windows-bridge` CI job (Windows tests never run yet).
4. Write `docs/REDEEM_REAL_COMPUTER_EXECUTION_REPORT.md` and README section (Clicky finding: Clicky only points with an overlay, never injects input; concepts adapted, no code copied; MIT).
5. Not built: WebRTC video (frames ~1/s instead), File Explorer/PDF scenario, case-via-portal scenario, vision/LLM planner (rule-based OCR planner only), live Bolna call (no credentials), VM-level cloud isolation.

Python env: use Python 3.12 (`/usr/bin/python3.12 -m venv .venv`), `pip install -r apps/api/requirements.txt pytest httpx`.
