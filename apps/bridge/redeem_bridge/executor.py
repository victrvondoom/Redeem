"""Executes validated actions on the local platform. Local pause / emergency stop / takeover always win over the server."""
from __future__ import annotations

import base64
import hashlib
import threading
import time

from . import protocol as P


class Executor:
    def __init__(self, platform):
        self.p = platform
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.takeover = threading.Event()
        self.frame_no = 0
        self.lock = threading.RLock()  # one OS call at a time: Xlib connections and SendInput sequences are not shareable across threads

    def blocked(self) -> str | None:
        if self.stopped.is_set():
            return "stopped"
        if self.takeover.is_set():
            return "user_has_control"
        if self.paused.is_set():
            return "paused"
        return None

    def observe(self, monitor: int = 0, region: dict | None = None, with_tree: bool = False) -> dict:
        with self.lock:
            return self._observe(monitor, region, with_tree)

    def _observe(self, monitor, region, with_tree):
        png, meta = self.p.capture(monitor, region)
        self.frame_no += 1
        cx, cy = self.p.cursor()
        obs = {"frame_no": self.frame_no, **meta, "sha256": hashlib.sha256(png).hexdigest(), "png_b64": base64.b64encode(png).decode(),
               "cursor": {"x": cx, "y": cy}, "active_window": self.p.active_window(), "windows": self.p.list_windows()[:40],
               "monitors": [m.__dict__ for m in self.p.monitors()]}
        if with_tree:
            obs["accessibility"] = self.p.accessibility_tree()
        return obs

    def run(self, action: str, params: dict, actor: str = "agent") -> dict:
        """actor="user" is the person driving from the REDEEM web view during a takeover; only an emergency stop blocks them."""
        try:
            p = P.validate(action, params)
        except P.InvalidAction as e:
            return {"ok": False, "error": "invalid_action", "detail": str(e)}
        if action in P.CONTROL:
            {"pause": self.paused.set, "resume": lambda: (self.paused.clear(), self.takeover.clear()), "stop": self.stopped.set,
             "request_takeover": self.takeover.set}.get(action, lambda: None)()
            return {"ok": True, "state": self.blocked() or "active"}
        if action == "ping":
            return {"ok": True, "state": self.blocked() or "active", "platform": self.p.name}
        if action in P.INPUT and (why := ("stopped" if self.stopped.is_set() else None) if actor == "user" else self.blocked()):
            return {"ok": False, "error": why, "detail": "input refused on the device"}
        with self.lock:  # one input sequence at a time
            res: dict = {}
            t0 = time.time()
            try:
                if action == "move_cursor":
                    self.p.move(p["x"], p["y"])
                elif action in ("click_coordinates", "click_element"):
                    self.p.click(p["x"], p["y"], p.get("button", "left"))
                elif action == "double_click":
                    self.p.click(p["x"], p["y"], p["button"], 2)
                elif action == "drag":
                    self.p.drag(p["x"], p["y"], p["to_x"], p["to_y"])
                elif action == "scroll":
                    self.p.scroll(p["x"], p["y"], p["dy"])
                elif action == "type_text":
                    res["typed"] = self.p.type_text(p["text"], should_stop=lambda: (self.stopped.is_set() if actor == "user" else self.blocked() is not None))
                    if res["typed"] < len(p["text"]):
                        return {"ok": False, "error": self.blocked() or "interrupted", "typed": res["typed"], "observation": self.observe()}
                elif action == "press_key":
                    for _ in range(p["repeat"]):
                        self.p.key(p["key"])
                elif action == "key_combination":
                    self.p.key(p["combo"])
                elif action == "focus_window":
                    res["focused"] = self.p.focus_window(p["window_id"])
                elif action == "launch_application":
                    res.update(self.p.launch(p["app"]))
                elif action == "open_url":
                    res.update(self.p.open_url(p["url"]))
                elif action == "list_windows":
                    return {"ok": True, "windows": self.p.list_windows()}
                elif action == "get_active_window":
                    return {"ok": True, "window": self.p.active_window()}
                elif action == "get_accessibility_tree":
                    return {"ok": True, "nodes": self.p.accessibility_tree()}
            except Exception as e:  # noqa: BLE001 - report every OS failure honestly
                return {"ok": False, "error": "os_error", "detail": f"{type(e).__name__}: {e}"[:300]}
            if action in P.INPUT:
                time.sleep(0.35)  # let the application repaint before the after-frame
            res["elapsed_ms"] = int((time.time() - t0) * 1000)
            res["observation"] = self.observe(p.get("monitor", 0), p.get("region"), with_tree=action == "observe_screen")
            return {"ok": True, **res}
