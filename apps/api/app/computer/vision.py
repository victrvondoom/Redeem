"""Screenshot-grounded vision planning (provider-backed) and honest capability reporting.

Nothing here simulates a model. `plan()` sends the real captured frame, with the accessibility/OCR context, to the configured
multimodal provider and validates the reply against `Proposal`. Model-supplied coordinates are never executed: a proposal is
only usable after `ground_proposal()` matches it to an element that the OCR/UIA pass found independently in the SAME frame.
With no credentials the status says so and `plan()` raises NotConfigured."""
from __future__ import annotations

import base64
import os
import threading
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..db import utcnow
from ..models import ComputerFrame
from . import grounding as G
from . import protocol as P

_lock = threading.Lock()
_last: dict = {"ok_at": None, "error": None, "tested_at": None, "test_ok": None}
API = "https://api.anthropic.com/v1/messages"


class NotConfigured(Exception):
    pass


class ProviderError(Exception):
    pass


class Box(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class Candidate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    kind: str = Field(max_length=30)
    bbox: Box
    basis: str = Field(max_length=300)  # why the model believes this is the element
    confidence: float | None = Field(default=None, ge=0, le=1)  # only if the provider supplied one; never invented


class Proposal(BaseModel):
    screen_summary: str = Field(max_length=800)
    candidates: list[Candidate] = Field(max_length=20)
    operation: str  # one of the bridge's INPUT actions
    target_label: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=1000)
    expected_result: str = Field(max_length=300)
    ambiguity: str | None = Field(default=None, max_length=300)
    needs_approval: bool = False


def _cfg() -> dict:
    prov = os.environ.get("REDEEM_VISION_PROVIDER", "").lower()
    key = os.environ.get("REDEEM_VISION_API_KEY", "") or (os.environ.get("ANTHROPIC_API_KEY", "") if prov in ("", "anthropic") else "")
    model = os.environ.get("REDEEM_VISION_MODEL", "")
    return {"provider": prov or ("anthropic" if key else ""), "key": key, "model": model}


def configured() -> bool:
    c = _cfg()
    return c["provider"] == "anthropic" and bool(c["key"] and c["model"])


def status() -> dict:
    c = _cfg()
    with _lock:
        last = dict(_last)
    if configured():
        state, detail = "configured", "credentials and model are set; use POST /api/v1/computer/vision/test to verify the connection"
    elif c["provider"] and c["provider"] != "anthropic":
        state, detail = "unsupported_provider", f"provider {c['provider']!r} has no adapter; only 'anthropic' is implemented"
    else:
        state, detail = "PROVIDER_NOT_CONFIGURED", "set REDEEM_VISION_PROVIDER=anthropic, REDEEM_VISION_API_KEY (or ANTHROPIC_API_KEY) and REDEEM_VISION_MODEL"
    return {"configured": configured(), "state": state, "provider": c["provider"] or None, "model": c["model"] or None, "detail": detail,
            "connection_test": {"status": "not_run" if last["test_ok"] is None else ("ok" if last["test_ok"] else "failed"), "at": last["tested_at"]},
            "last_successful_operation_at": last["ok_at"], "last_error": last["error"]}


def perception_modes() -> list[dict]:
    """Separate, explicitly identified capabilities. The OCR path is real but is not a vision model."""
    return [{"id": "ocr_grounding", "kind": "non-LLM", "available": True, "detail": "OCR text boxes of the captured frame; window title from the bridge"},
            {"id": "vision_model", "kind": "multimodal model", "available": configured(), "detail": status()["detail"]}]


def _record(ok: bool, err: str | None = None, test: bool = False):
    with _lock:
        now = utcnow().isoformat()
        if ok:
            _last["ok_at"], _last["error"] = now, None
        else:
            _last["error"] = err
        if test:
            _last["tested_at"], _last["test_ok"] = now, ok


PROMPT = ("You see one real screenshot of a computer. Reply with ONLY a JSON object with keys: screen_summary, candidates (list of {label, kind, bbox:{x,y,w,h} in screenshot pixels, "
          "basis, confidence optional}), operation (one of: {ops}), target_label, text, expected_result, ambiguity, needs_approval. Do not invent elements that are not visible. "
          "Task: {task}")


def plan(frame: ComputerFrame, task: str, *, transport: httpx.BaseTransport | None = None) -> Proposal:
    if not configured():
        raise NotConfigured("PROVIDER_NOT_CONFIGURED")
    c = _cfg()
    img = base64.b64encode(Path(frame.path).read_bytes()).decode()
    body = {"model": c["model"], "max_tokens": 1500, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
        {"type": "text", "text": PROMPT.format(ops=", ".join(sorted(P.INPUT)), task=task[:500])}]}]}
    try:
        with httpx.Client(timeout=60, transport=transport) as h:
            r = h.post(API, json=body, headers={"x-api-key": c["key"], "anthropic-version": "2023-06-01"})
        if r.status_code != 200:
            raise ProviderError(f"provider returned HTTP {r.status_code}")
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        import json
        raw = json.loads(text[text.index("{"): text.rindex("}") + 1])
        prop = Proposal.model_validate(raw)
    except (httpx.HTTPError, ProviderError, ValueError, ValidationError) as e:
        msg = f"{type(e).__name__}: {str(e)[:200]}"
        _record(False, msg)
        raise ProviderError(msg) from e
    if prop.operation not in P.INPUT:
        _record(False, "operation outside the bridge protocol")
        raise ProviderError(f"model proposed unsupported operation {prop.operation!r}")
    for cd in prop.candidates:
        if cd.bbox.x + cd.bbox.w > frame.width or cd.bbox.y + cd.bbox.h > frame.height:
            _record(False, "bounding box outside the frame")
            raise ProviderError("model returned a bounding box outside the screenshot")
    _record(True)
    return prop


def ground_proposal(frame: ComputerFrame, latest_frame_id: str | None, prop: Proposal) -> dict:
    """Return an executable target only if (a) the frame is still the newest and (b) the proposed element overlaps text that OCR independently found in that frame.
    Raw model coordinates are never returned as an action; the target comes from the independent perception."""
    if latest_frame_id != frame.id:
        return {"ok": False, "reason": "stale_frame", "detail": "the screen changed since this frame; observe again"}
    if prop.ambiguity or len(prop.candidates) != 1 and prop.target_label is None:
        return {"ok": False, "reason": "ambiguous", "detail": prop.ambiguity or "several candidates and no target label"}
    label = prop.target_label or prop.candidates[0].label
    hit = G.find(frame, label)
    if not hit:
        return {"ok": False, "reason": "not_grounded", "detail": f"OCR did not find {label!r} in the same frame"}
    cd = next((c for c in prop.candidates if c.label.lower() == label.lower()), prop.candidates[0] if prop.candidates else None)
    if cd:
        cx, cy = cd.bbox.x + cd.bbox.w / 2, cd.bbox.y + cd.bbox.h / 2
        if abs(cx - hit["x"] + frame.origin_x) > max(cd.bbox.w, 60) or abs(cy - hit["y"] + frame.origin_y) > max(cd.bbox.h, 40):
            return {"ok": False, "reason": "disagreement", "detail": "the model's box and the OCR location of that label do not agree"}
    return {"ok": True, "target": hit}
