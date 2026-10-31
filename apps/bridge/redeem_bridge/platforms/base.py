from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Monitor:
    index: int
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


class Platform:
    """What the executor needs from an OS. Coordinates are virtual-desktop pixels."""

    name = "base"

    def monitors(self) -> list[Monitor]:
        import mss
        with mss.mss() as s:
            mons = s.monitors[1:] or s.monitors[:1]
            return [Monitor(i, m["left"], m["top"], m["width"], m["height"], i == 0) for i, m in enumerate(mons)]

    def capture(self, monitor: int = 0, region: dict | None = None) -> tuple[bytes, dict]:
        """PNG bytes of a monitor (or a region of it) plus geometry metadata."""
        import mss
        import mss.tools
        mons = self.monitors()
        m = mons[min(monitor, len(mons) - 1)]
        box = {"left": m.x, "top": m.y, "width": m.width, "height": m.height}
        if region:
            box = {"left": m.x + region["x"], "top": m.y + region["y"], "width": region["w"], "height": region["h"]}
        with mss.mss() as s:
            img = s.grab(box)
            png = mss.tools.to_png(img.rgb, img.size)
        return png, {"monitor": m.index, "origin_x": box["left"], "origin_y": box["top"], "width": img.size[0], "height": img.size[1],
                     "scale": 1.0, "captured_at": time.time()}

    # input
    def move(self, x: int, y: int) -> None: raise NotImplementedError
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None: raise NotImplementedError
    def drag(self, x: int, y: int, to_x: int, to_y: int) -> None: raise NotImplementedError
    def scroll(self, x: int, y: int, dy: int) -> None: raise NotImplementedError
    def type_text(self, text: str, should_stop=lambda: False) -> int: raise NotImplementedError
    def key(self, combo: str) -> None: raise NotImplementedError
    def cursor(self) -> tuple[int, int]: raise NotImplementedError
    # windows
    def list_windows(self) -> list[dict]: return []
    def active_window(self) -> dict | None: return None
    def focus_window(self, window_id: str) -> bool: return False
    def accessibility_tree(self, max_nodes: int = 200) -> list[dict]: return []
    # launch
    def launch(self, app: str) -> dict: raise NotImplementedError
    def open_url(self, url: str) -> dict: raise NotImplementedError
