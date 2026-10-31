"""Native Windows integration tests: real Notepad, real SendInput, real clipboard and UI Automation.
Run on Windows 10/11 or the windows-latest CI runner: pytest apps/bridge/tests/test_windows.py"""
import ctypes
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture
def notepad():
    from redeem_bridge.platforms.windows import WindowsPlatform
    p = WindowsPlatform()
    before = {w["id"] for w in p.list_windows()}
    info = p.launch("notepad")
    win = None
    for _ in range(50):
        new = [w for w in p.list_windows() if w["id"] not in before and "notepad" in (w["app"] or "").lower()]
        if new:
            win = new[0]
            break
        time.sleep(0.2)
    assert win, "Notepad window did not appear"
    yield p, win
    subprocess.run(["taskkill", "/F", "/PID", str(win["pid"])], capture_output=True)
    if info.get("pid"):
        subprocess.run(["taskkill", "/F", "/PID", str(info["pid"])], capture_output=True)


def _clipboard_text():
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    k.GlobalLock.restype = ctypes.c_void_p
    u.GetClipboardData.restype = ctypes.c_void_p
    for _ in range(20):
        if u.OpenClipboard(0):
            break
        time.sleep(0.1)
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        return ctypes.wstring_at(k.GlobalLock(h)) if h else ""
    finally:
        if h:
            k.GlobalUnlock(ctypes.c_void_p(h))
        u.CloseClipboard()


def test_capture_monitors_and_cursor():
    from redeem_bridge.platforms.windows import WindowsPlatform
    p = WindowsPlatform()
    mons = p.monitors()
    assert mons and mons[0].width > 0
    png, meta = p.capture(0)
    assert png[:4] == b"\x89PNG" and meta["width"] == mons[0].width
    p.move(mons[0].x + 123, mons[0].y + 77)
    assert p.cursor() == (mons[0].x + 123, mons[0].y + 77)


def test_focus_type_shortcuts_and_read_back_in_notepad(notepad):
    p, win = notepad
    assert p.focus_window(win["id"])
    assert "notepad" in (p.active_window()["app"] or "").lower()
    p.click(win["x"] + win["width"] // 2, win["y"] + win["height"] // 2)
    text = "REDEEM bridge test 42 - ₹ ünïcode"
    assert p.type_text(text) == len(text)
    p.key("ctrl+a")
    p.key("ctrl+c")
    time.sleep(0.3)
    assert _clipboard_text().strip().endswith(text)
    nodes = p.accessibility_tree()
    assert nodes, "UI Automation returned no elements"
    assert any(text in (n.get("value") or "") or text in (n.get("name") or "") for n in nodes) or any(n["role"] in ("DocumentControl", "EditControl") for n in nodes)


def test_executor_pause_blocks_real_input(notepad):
    from redeem_bridge.executor import Executor
    p, win = notepad
    ex = Executor(p)
    ex.paused.set()
    r = ex.run("type_text", {"text": "should not appear"})
    assert not r["ok"] and r["error"] == "paused"
    ex.paused.clear()
    r = ex.run("observe_screen", {})
    assert r["ok"] and r["observation"]["active_window"] is not None and r["observation"]["windows"]
