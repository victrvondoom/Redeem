"""The computer-action protocol shared by the REDEEM server and the bridge. Every action is validated on both sides."""
from __future__ import annotations

import re

KEYS = {"enter", "return", "tab", "escape", "esc", "backspace", "delete", "space", "home", "end", "pageup", "pagedown",
        "up", "down", "left", "right", *[f"f{i}" for i in range(1, 13)], "ctrl", "alt", "shift", "win", "super", "cmd"}
# Shortcuts that would act on the whole system rather than the focused app are refused (lock, sign-out, task manager...).
BLOCKED_COMBOS = {"ctrl+alt+delete", "win+l", "super+l", "ctrl+alt+del", "ctrl+shift+escape", "ctrl+shift+esc", "alt+f4+win", "win+r", "super+r"}
APPS = {"browser", "notepad", "explorer", "vscode", "calculator"}  # launch is by allow-listed id, never by a path from model text
INPUT = {"move_cursor", "click_coordinates", "double_click", "click_element", "type_text", "press_key", "key_combination", "scroll", "drag",
         "focus_window", "launch_application", "open_url"}
READ = {"observe_screen", "capture_screenshot", "get_active_window", "list_windows", "get_accessibility_tree", "find_element", "wait_for_state", "verify_state", "ping"}
CONTROL = {"pause", "resume", "stop", "request_takeover", "start_recording", "stop_recording"}
ACTIONS = INPUT | READ | CONTROL


class InvalidAction(ValueError):
    pass


def _int(p, k, lo=-100000, hi=100000):
    v = p.get(k)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise InvalidAction(f"{k} must be an integer in [{lo}, {hi}]")
    return v


def normalize_combo(combo: str) -> str:
    parts = [p.strip().lower() for p in str(combo).split("+") if p.strip()]
    if not 1 <= len(parts) <= 4:
        raise InvalidAction("key combination needs 1 to 4 keys")
    for p in parts:
        if p not in KEYS and not re.fullmatch(r"[a-z0-9]", p):
            raise InvalidAction(f"unknown key {p!r}")
    c = "+".join(parts)
    if c in BLOCKED_COMBOS or (("win" in parts or "super" in parts) and len(parts) > 1):
        raise InvalidAction(f"system-level shortcut {c!r} is not allowed")
    return c


def validate(action: str, params: dict) -> dict:
    """Return a cleaned copy of params or raise InvalidAction. Unknown keys are dropped."""
    if action not in ACTIONS:
        raise InvalidAction(f"unknown action {action!r}")
    p = dict(params or {})
    out: dict = {}
    if action in ("move_cursor", "click_coordinates", "click_element", "double_click"):
        out = {"x": _int(p, "x"), "y": _int(p, "y")}
        if action != "move_cursor":
            out["button"] = p.get("button", "left")
            if out["button"] not in ("left", "right", "middle"):
                raise InvalidAction("button must be left, right or middle")
    elif action == "drag":
        out = {k: _int(p, k) for k in ("x", "y", "to_x", "to_y")}
    elif action == "scroll":
        out = {"x": _int(p, "x"), "y": _int(p, "y"), "dy": _int(p, "dy", -50, 50)}
    elif action == "type_text":
        t = p.get("text")
        if not isinstance(t, str) or not 0 < len(t) <= 2000:
            raise InvalidAction("text must be 1-2000 characters")
        if any(ord(ch) < 32 and ch not in "\n\t" for ch in t):
            raise InvalidAction("text may not contain control characters")
        out = {"text": t}
    elif action == "press_key":
        k = str(p.get("key", "")).lower()
        if k not in KEYS and not re.fullmatch(r"[a-z0-9]", k):
            raise InvalidAction(f"unknown key {k!r}")
        out = {"key": k, "repeat": _int({"r": p.get("repeat", 1)}, "r", 1, 20)}
    elif action == "key_combination":
        out = {"combo": normalize_combo(p.get("combo", ""))}
    elif action == "focus_window":
        out = {"window_id": str(p.get("window_id", ""))[:40]}
        if not out["window_id"]:
            raise InvalidAction("window_id required")
    elif action == "launch_application":
        if p.get("app") not in APPS:
            raise InvalidAction(f"app must be one of {sorted(APPS)}")
        out = {"app": p["app"]}
    elif action == "open_url":
        u = str(p.get("url", ""))
        if not re.fullmatch(r"https?://[^\s\"'<>]{1,500}", u):
            raise InvalidAction("url must be an http(s) URL")
        out = {"url": u}
    elif action in ("observe_screen", "capture_screenshot"):
        out = {"monitor": _int({"m": p.get("monitor", 0)}, "m", 0, 16)}
        if p.get("region"):
            r = p["region"]
            out["region"] = {k: _int(r, k, 0, 100000) for k in ("x", "y", "w", "h")}
    return out
