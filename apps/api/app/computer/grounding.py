"""Visual grounding: find a UI target in a specific captured frame (OCR text boxes) and map it to screen coordinates.

A target is always tied to the frame it was found in. The pipeline refuses to act on a target whose frame is no
longer the newest one for the session, so stale coordinates are never reused."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from .. import ocr
from ..models import ComputerFrame

_cache: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9@.+:/-]", "", s.lower())  # OCR often drops or adds spaces, so compare without them


def elements(frame: ComputerFrame) -> list[dict]:
    with _lock:
        if frame.id in _cache:
            return _cache[frame.id]
    boxes = ocr.read_boxes(Path(frame.path).read_bytes())
    sx = 1.0  # bridge captures at physical pixels with DPI awareness on, so frame pixels == screen pixels
    els = [{**b, "role": "text", "screen_x": frame.origin_x + int((b["x"] + b["w"] / 2) * sx), "screen_y": frame.origin_y + int((b["y"] + b["h"] / 2) * sx)} for b in boxes]
    with _lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[frame.id] = els
    return els


def texts(frame: ComputerFrame) -> str:
    return "\n".join(e["text"] for e in sorted(elements(frame), key=lambda e: (e["y"] // 12, e["x"])))


def has(frame: ComputerFrame, phrase: str) -> bool:
    n = _norm(phrase)
    return n in _norm(" ".join(e["text"] for e in elements(frame))) or any(n in _norm(e["text"]) for e in elements(frame))


def has_fuzzy(frame: ComputerFrame, phrase: str, ratio: float = 0.8) -> bool:
    """Tolerates OCR slips in long identifiers: true if one OCR run shares a contiguous stretch of >= ratio of the phrase."""
    from difflib import SequenceMatcher
    n = _norm(phrase)
    if not n:
        return False
    return any(SequenceMatcher(None, n, _norm(e["text"]), autojunk=False).find_longest_match(0, len(n), 0, len(_norm(e["text"]))).size >= ratio * len(n) for e in elements(frame))


def find(frame: ComputerFrame, label: str, min_conf: float = 0.5, below_y: int | None = None, lowest: bool = False) -> dict | None:
    """Best element whose text matches label: exact > starts-with > contains. Returns a grounded target."""
    n = _norm(label)
    best, score = None, 0
    for e in elements(frame):
        if e["conf"] < min_conf or (below_y is not None and e["y"] < below_y):
            continue
        t = _norm(e["text"])
        s = 3 if t == n else 2 if t.startswith(n) else 1 if n and n in t else 0
        if s > score or (s == score and s and best and ((e["y"] > best["y"]) if lowest else (len(t), -e["conf"]) < (len(_norm(best["text"])), -best["conf"]))):
            best, score = e, s
    if not best:
        return None
    bx, bw, sx = best["x"], best["w"], best["screen_x"]
    t = best["text"]
    i = t.lower().find(label.lower())
    if i < 0:  # OCR spacing differs from the label: locate it on the compacted text instead
        compact = re.sub(r"\s", "", t.lower())
        j = compact.find(re.sub(r"\s", "", label.lower()))
        i, t_len = (j, len(compact)) if j >= 0 else (-1, len(t))
    else:
        t_len = len(t)
    if score < 3 and i >= 0 and t_len > len(label):  # label is part of a longer OCR run: aim at the label's own span
        cw = best["w"] / max(t_len, 1)
        bx, bw = int(best["x"] + i * cw), max(int(len(label) * cw), 6)
        sx = frame.origin_x + bx + bw // 2
    return {"label": label, "text": t, "frame_id": frame.id, "x": sx, "y": best["screen_y"],
            "bbox": {"x": bx, "y": best["y"], "w": bw, "h": best["h"]}, "confidence": best["conf"], "match": score,
            "monitor": frame.monitor, "frame_size": {"w": frame.width, "h": frame.height}}
