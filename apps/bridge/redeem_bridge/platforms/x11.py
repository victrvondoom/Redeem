"""X11 backend (Linux desktops and REDEEM's cloud computer). Input is injected with the XTEST extension, which the
X server treats exactly like a physical mouse and keyboard; capture uses MIT-SHM/XGetImage through mss."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time

from Xlib import X, XK, display
from Xlib.ext import xtest

from .base import Platform

_NAMES = {"enter": "Return", "return": "Return", "tab": "Tab", "escape": "Escape", "esc": "Escape", "backspace": "BackSpace", "delete": "Delete",
          "space": "space", "home": "Home", "end": "End", "pageup": "Page_Up", "pagedown": "Page_Down", "up": "Up", "down": "Down", "left": "Left",
          "right": "Right", "ctrl": "Control_L", "alt": "Alt_L", "shift": "Shift_L", "win": "Super_L", "super": "Super_L", "cmd": "Super_L",
          **{f"f{i}": f"F{i}" for i in range(1, 13)}}
_BUTTON = {"left": 1, "middle": 2, "right": 3}


class X11Platform(Platform):
    name = "x11"

    def __init__(self, display_name: str | None = None):
        self.d = display.Display(display_name or os.environ.get("DISPLAY"))
        self.root = self.d.screen().root
        self._procs: list[subprocess.Popen] = []

    # ---------------------------------------------------------------- input
    def _sync(self):
        self.d.sync()

    def move(self, x, y):
        xtest.fake_input(self.d, X.MotionNotify, x=x, y=y)
        self._sync()

    def cursor(self):
        p = self.root.query_pointer()
        return p.root_x, p.root_y

    def click(self, x, y, button="left", count=1):
        self.move(x, y)
        b = _BUTTON[button]
        for _ in range(count):
            xtest.fake_input(self.d, X.ButtonPress, b)
            xtest.fake_input(self.d, X.ButtonRelease, b)
            self._sync()
            time.sleep(0.05)

    def drag(self, x, y, to_x, to_y):
        self.move(x, y)
        xtest.fake_input(self.d, X.ButtonPress, 1)
        self._sync()
        for i in range(1, 11):
            self.move(x + (to_x - x) * i // 10, y + (to_y - y) * i // 10)
            time.sleep(0.02)
        xtest.fake_input(self.d, X.ButtonRelease, 1)
        self._sync()

    def scroll(self, x, y, dy):
        self.move(x, y)
        b = 5 if dy > 0 else 4
        for _ in range(abs(dy)):
            xtest.fake_input(self.d, X.ButtonPress, b)
            xtest.fake_input(self.d, X.ButtonRelease, b)
        self._sync()

    def _keycode(self, keysym):
        kc = self.d.keysym_to_keycode(keysym)
        if kc:
            shifted = self.d.keycode_to_keysym(kc, 0) != keysym and self.d.keycode_to_keysym(kc, 1) == keysym
            return kc, shifted
        # character not on the keyboard map: borrow the last keycode, as xdotool does
        kc = self.d.display.info.max_keycode - 1
        self.d.change_keyboard_mapping(kc, [(keysym,) * 4])
        self._sync()
        return kc, False

    def _tap(self, kc, shifted=False):
        sh = self.d.keysym_to_keycode(XK.string_to_keysym("Shift_L"))
        if shifted:
            xtest.fake_input(self.d, X.KeyPress, sh)
        xtest.fake_input(self.d, X.KeyPress, kc)
        xtest.fake_input(self.d, X.KeyRelease, kc)
        if shifted:
            xtest.fake_input(self.d, X.KeyRelease, sh)
        self._sync()

    def type_text(self, text, should_stop=lambda: False):
        n = 0
        for ch in text:
            if should_stop():
                break
            if ch == "\n":
                ks = XK.string_to_keysym("Return")
            elif ch == "\t":
                ks = XK.string_to_keysym("Tab")
            else:
                ks = XK.string_to_keysym(XK.keysym_to_string(ord(ch)) or "") or (ord(ch) if ord(ch) < 256 else 0x01000000 + ord(ch))
            kc, shifted = self._keycode(ks)
            self._tap(kc, shifted)
            n += 1
            time.sleep(0.008)
        return n

    def key(self, combo):
        parts = combo.split("+")
        codes = []
        for p in parts:
            ks = XK.string_to_keysym(_NAMES.get(p, p))
            codes.append(self._keycode(ks)[0])
        for kc in codes:
            xtest.fake_input(self.d, X.KeyPress, kc)
        for kc in reversed(codes):
            xtest.fake_input(self.d, X.KeyRelease, kc)
        self._sync()

    # ---------------------------------------------------------------- windows
    def _info(self, w):
        try:
            name = w.get_wm_name()
            cls = w.get_wm_class()
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            g = w.get_geometry()
            pos = w.translate_coords(self.root, 0, 0)
            attrs = w.get_attributes()
            return {"id": hex(w.id), "title": name or "", "app": (cls[1] if cls else "") or "", "x": -pos.x, "y": -pos.y, "width": g.width,
                    "height": g.height, "visible": attrs.map_state == X.IsViewable}
        except Exception:
            return None

    def _top(self):
        out = []
        for w in self.root.query_tree().children:
            for c in [w, *w.query_tree().children]:
                i = self._info(c)
                if i and i["visible"] and (i["title"] or i["app"]) and i["width"] > 50:
                    out.append(i)
                    break
        return out

    def list_windows(self):
        return self._top()

    def active_window(self):
        f = self.d.get_input_focus().focus
        if not f or isinstance(f, int):
            return None
        w = f
        for _ in range(6):
            i = self._info(w)
            if i and i["title"]:
                return i
            q = w.query_tree()
            if not q.parent or q.parent.id == self.root.id:
                break
            w = q.parent
        return self._info(f)

    def focus_window(self, window_id):
        w = self.d.create_resource_object("window", int(window_id, 16))
        w.configure(stack_mode=X.Above)
        w.set_input_focus(X.RevertToParent, X.CurrentTime)
        self._sync()
        return True

    # ---------------------------------------------------------------- launch (allow-listed ids only)
    def _browser(self):
        for p in (os.environ.get("REDEEM_BRIDGE_BROWSER"), "/opt/pw-browsers/chromium", shutil.which("chromium"), shutil.which("google-chrome")):
            if p and os.path.exists(p):
                return p
        raise RuntimeError("no browser found (set REDEEM_BRIDGE_BROWSER)")

    def open_url(self, url):
        prof = os.environ.get("REDEEM_BRIDGE_PROFILE") or tempfile.mkdtemp(prefix="redeem-browser-")
        w, h = self.monitors()[0].width, self.monitors()[0].height
        args = [self._browser(), "--no-sandbox", "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--disable-dev-shm-usage",
                f"--user-data-dir={prof}", "--window-position=0,0", f"--window-size={w},{h}", "--force-device-scale-factor=1", url]
        self._procs.append(subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ}))
        return {"pid": self._procs[-1].pid}

    def launch(self, app):
        if app == "browser":
            return self.open_url("about:blank")
        raise RuntimeError(f"{app} is not available on this Linux desktop")

    def close(self):
        for p in self._procs:
            p.terminate()
