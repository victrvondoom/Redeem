"""Windows 10/11 backend. Real input through user32 SendInput (the same path as a physical device), window discovery
through EnumWindows, application state through Windows UI Automation, capture through GDI (mss).

Runs as a normal user. It cannot drive elevated (administrator) windows, which is Windows' own UIPI protection."""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from ctypes import wintypes as W

from .base import Platform

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:  # per-monitor DPI awareness so screen pixels, capture pixels and input coordinates agree
    u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", W.DWORD), ("wParamL", W.WORD), ("wParamH", W.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", W.DWORD), ("u", _U)]


MOVE, LDOWN, LUP, RDOWN, RUP, MDOWN, MUP, WHEEL, VDESK, ABS = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x800, 0x4000, 0x8000
KEYUP, UNICODE = 0x2, 0x4
VK = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B, "backspace": 0x08, "delete": 0x2E, "space": 0x20, "home": 0x24,
      "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "ctrl": 0x11, "alt": 0x12,
      "shift": 0x10, "win": 0x5B, "super": 0x5B, "cmd": 0x5B, **{f"f{i}": 0x6F + i for i in range(1, 13)}}
BTN = {"left": (LDOWN, LUP), "right": (RDOWN, RUP), "middle": (MDOWN, MUP)}
u32.SendInput.argtypes = (W.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
EnumProc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def _send(*inputs: INPUT) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    if u32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError(f"SendInput was blocked (error {ctypes.get_last_error()}); the target may be an elevated window or the desktop is locked")


def _mouse(flags, dx=0, dy=0, data=0):
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return i


def _key(vk=0, scan=0, flags=0):
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


class WindowsPlatform(Platform):
    name = "windows"

    def _norm(self, x, y):
        vx, vy, vw, vh = (u32.GetSystemMetrics(i) for i in (76, 77, 78, 79))
        return int((x - vx) * 65535 / max(vw - 1, 1)), int((y - vy) * 65535 / max(vh - 1, 1))

    def move(self, x, y):
        nx, ny = self._norm(x, y)
        _send(_mouse(MOVE | ABS | VDESK, nx, ny))

    def cursor(self):
        p = W.POINT()
        u32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def click(self, x, y, button="left", count=1):
        self.move(x, y)
        d, u = BTN[button]
        for _ in range(count):
            _send(_mouse(d), _mouse(u))
            time.sleep(0.05)

    def drag(self, x, y, to_x, to_y):
        self.move(x, y)
        _send(_mouse(LDOWN))
        for i in range(1, 11):
            self.move(x + (to_x - x) * i // 10, y + (to_y - y) * i // 10)
            time.sleep(0.02)
        _send(_mouse(LUP))

    def scroll(self, x, y, dy):
        self.move(x, y)
        _send(_mouse(WHEEL, data=-120 * dy))

    def type_text(self, text, should_stop=lambda: False):
        n = 0
        for ch in text:
            if should_stop():
                break
            if ch == "\n":
                _send(_key(0x0D), _key(0x0D, flags=KEYUP))
            else:
                for unit in ch.encode("utf-16-le").hex(" ", 2).split():  # surrogate pairs are sent as two units
                    code = int(unit[2:] + unit[:2], 16)
                    _send(_key(0, code, UNICODE), _key(0, code, UNICODE | KEYUP))
            n += 1
            time.sleep(0.005)
        return n

    def key(self, combo):
        vks = [VK.get(p) or ord(p.upper()) for p in combo.split("+")]
        _send(*[_key(v) for v in vks], *[_key(v, flags=KEYUP) for v in reversed(vks)])

    # ---------------------------------------------------------------- windows
    def _info(self, h):
        n = u32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, buf, n + 1)
        r = W.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        pid = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        exe = ""
        hp = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if hp:
            size = W.DWORD(520)
            pb = ctypes.create_unicode_buffer(520)
            if k32.QueryFullProcessImageNameW(hp, 0, pb, ctypes.byref(size)):
                exe = os.path.basename(pb.value)
            k32.CloseHandle(hp)
        return {"id": hex(h), "title": buf.value, "app": exe, "pid": pid.value, "x": r.left, "y": r.top, "width": r.right - r.left,
                "height": r.bottom - r.top, "visible": bool(u32.IsWindowVisible(h)), "minimized": bool(u32.IsIconic(h))}

    def list_windows(self):
        out = []

        def cb(h, _):
            if u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h) and not u32.GetWindow(h, 4):  # visible, titled, unowned
                out.append(self._info(h))
            return True
        u32.EnumWindows(EnumProc(cb), 0)
        return out

    def active_window(self):
        h = u32.GetForegroundWindow()
        return self._info(h) if h else None

    def focus_window(self, window_id):
        h = int(window_id, 16)
        if u32.IsIconic(h):
            u32.ShowWindow(h, 9)  # SW_RESTORE
        _send(_key(0x12), _key(0x12, flags=KEYUP))  # an ALT tap lets this process take the foreground (documented SetForegroundWindow rule)
        u32.SetForegroundWindow(h)
        time.sleep(0.15)
        return u32.GetForegroundWindow() == h

    def accessibility_tree(self, max_nodes=200):
        try:
            import uiautomation as auto  # optional dependency (pip install uiautomation)
        except ImportError:
            return []
        root = auto.GetForegroundControl()
        out = []

        def walk(c, depth, parent):
            if len(out) >= max_nodes or depth > 12:
                return
            r = c.BoundingRectangle
            node = {"id": len(out), "parent": parent, "name": c.Name, "role": c.ControlTypeName, "x": r.left, "y": r.top,
                    "width": r.width(), "height": r.height(), "enabled": c.IsEnabled, "focused": c.HasKeyboardFocus}
            try:
                vp = c.GetValuePattern()
                node["value"] = vp.Value[:500]
            except Exception:
                pass
            out.append(node)
            for ch in c.GetChildren():
                walk(ch, depth + 1, node["id"])
        walk(root, 0, None)
        return out

    # ---------------------------------------------------------------- launch (allow-listed ids only, never a model-supplied path)
    def launch(self, app):
        exe = {"notepad": "notepad.exe", "explorer": "explorer.exe", "calculator": "calc.exe", "vscode": shutil.which("code") or ""}.get(app)
        if app == "browser":
            os.startfile("https://www.bing.com")  # default browser
            return {"launched": "default browser"}
        if not exe:
            raise RuntimeError(f"{app} is not installed")
        p = subprocess.Popen([exe])
        return {"pid": p.pid}

    def open_url(self, url):
        os.startfile(url)  # validated http(s) only; opens in the user's default browser
        return {"opened": url}
