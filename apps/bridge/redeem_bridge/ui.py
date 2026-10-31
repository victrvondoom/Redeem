"""Bridge window and pointer overlay (Tk; bundled with python.org builds on Windows).

The window is always visible while the bridge runs: it says when REDEEM is controlling the computer and gives
Pause, Resume, Take over and Emergency stop. The overlay is an orange ring drawn where REDEEM is about to act; it is
click-through, so it never intercepts the user's own clicks."""
from __future__ import annotations

import sys
import threading
import tkinter as tk

ORANGE, BG, FG = "#ff7a1a", "#141210", "#f3efe9"


def _click_through(win: tk.Toplevel) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    h = ctypes.windll.user32.GetParent(win.winfo_id())
    ex = ctypes.windll.user32.GetWindowLongW(h, -20)
    ctypes.windll.user32.SetWindowLongW(h, -20, ex | 0x80000 | 0x20)  # WS_EX_LAYERED | WS_EX_TRANSPARENT


def run_with_ui(bridge) -> None:
    root = tk.Tk()
    root.title("REDEEM Computer Bridge")
    root.configure(bg=BG)
    root.attributes("-topmost", True)
    root.geometry("340x190+20+20")
    state = tk.StringVar(value="Connecting…")
    tk.Label(root, text="REDEEM Computer Bridge", bg=BG, fg=FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
    tk.Label(root, textvariable=state, bg=BG, fg=ORANGE, font=("Segoe UI", 10), wraplength=310, justify="left").pack(anchor="w", padx=12, pady=6)
    row = tk.Frame(root, bg=BG)
    row.pack(fill="x", padx=12)
    for label, op in (("Pause", "pause"), ("Resume", "resume"), ("Take over", "request_takeover")):
        tk.Button(row, text=label, command=lambda o=op: bridge.local(o)).pack(side="left", padx=(0, 6))
    tk.Button(root, text="EMERGENCY STOP", bg="#b3261e", fg="white", command=lambda: (bridge.local("stop"), state.set("Stopped. No more input will be sent."))).pack(fill="x", padx=12, pady=8)

    ov = tk.Toplevel(root)
    ov.overrideredirect(True)
    ov.attributes("-topmost", True)
    if sys.platform == "win32":
        ov.attributes("-transparentcolor", "black")
    ov.configure(bg="black")
    cv = tk.Canvas(ov, width=64, height=64, bg="black", highlightthickness=0)
    cv.pack()
    cv.create_oval(6, 6, 58, 58, outline=ORANGE, width=4)
    cv.create_oval(28, 28, 36, 36, fill=ORANGE, outline=ORANGE)
    ov.withdraw()
    root.after(200, lambda: _click_through(ov))

    def show_target(x, y, label):
        def go():
            ov.geometry(f"64x64+{x - 32}+{y - 32}")
            ov.deiconify()
            root.after(1500, ov.withdraw)
        root.after(0, go)
    bridge.on_target = show_target
    bridge.on_status = lambda s: root.after(0, lambda: state.set(("REDEEM is controlling this computer. " if s.startswith(("click", "type", "press", "key", "open", "launch", "move", "drag", "scroll", "focus")) else "") + s))
    threading.Thread(target=bridge.run_forever, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", lambda: (bridge.local("stop"), bridge.quit.set(), root.destroy()))
    root.mainloop()
