"""Real OCR (RapidOCR / ONNX Runtime, models ship inside the wheel; no network or system binary needed).
Returns text grouped into lines plus a mean confidence, so the UI can offer review and correction. Never invents text."""
from __future__ import annotations

import io
import threading

_engine = None
_lock = threading.Lock()


def available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _get():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        return _engine


def read_image(data: bytes) -> tuple[str, float]:
    """-> (text with one line per detected text row, mean confidence 0..1). ('' , 0.0) when nothing is legible."""
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    res, _ = _get()(np.array(img))
    if not res:
        return "", 0.0
    boxes = [(sum(p[1] for p in b[0]) / 4, min(p[0] for p in b[0]), b[1], float(b[2])) for b in res]  # (cy, x, text, conf)
    boxes.sort(key=lambda t: t[0])
    heights = sorted(max(p[1] for p in b[0]) - min(p[1] for p in b[0]) for b in res)
    tol = max(8.0, heights[len(heights) // 2] * 0.6)
    lines: list[list[tuple[float, float, str, float]]] = []
    for b in boxes:
        if lines and abs(lines[-1][-1][0] - b[0]) <= tol:
            lines[-1].append(b)
        else:
            lines.append([b])
    text = "\n".join(" ".join(t[2] for t in sorted(ln, key=lambda t: t[1])) for ln in lines)
    return text, round(sum(b[3] for b in boxes) / len(boxes), 3)


def read_boxes(data: bytes) -> list[dict]:
    """Every detected text run with its pixel box in the image: [{text, x, y, w, h, conf}]. Used to ground UI targets."""
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    res, _ = _get()(np.array(img))
    out = []
    for quad, text, conf in res or []:
        xs, ys = [p[0] for p in quad], [p[1] for p in quad]
        out.append({"text": text, "x": int(min(xs)), "y": int(min(ys)), "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys)), "conf": round(float(conf), 3)})
    return out
