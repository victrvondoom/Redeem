"""Personal-workspace tools inherited from RESOLVE: sandboxed file workflow (inventory, content-hash dedupe, dry-run plan, temporal guard, journalled apply,
undo) and the PDF document studio (rotate / remove pages / merge / create report, with source-hash guard). One sandbox per tenant under REDEEM_DATA_DIR."""
import json
import os
import re
import shutil
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from ..config import settings
from ..core.deps import Ctx, audit, current_ctx, err
from ..resolve.document_studio import DocumentError, DocumentStudio
from ..resolve.file_worker import FileWorker, FileWorkerError
from ..schemas import ApplyPlanIn, ReportIn, TransformIn, UndoIn

router = APIRouter(prefix="/api/v1", tags=["workspace"])
_lock = threading.Lock()
_fw: dict[str, FileWorker] = {}
_ds: dict[str, DocumentStudio] = {}
MAX_UPLOAD = 20 * 1024 * 1024


def _root(tenant: str, kind: str) -> Path:
    return Path(settings.data_dir) / kind / tenant


def fw(tenant: str) -> FileWorker:
    with _lock:
        if tenant not in _fw:
            sb = _root(tenant, "files") / "sandbox"
            sb.mkdir(parents=True, exist_ok=True)
            _fw[tenant] = FileWorker(sb, _root(tenant, "files") / "journal.sqlite3")
        return _fw[tenant]


def ds(tenant: str) -> DocumentStudio:
    with _lock:
        if tenant not in _ds:
            _ds[tenant] = DocumentStudio(_root(tenant, "studio"))
        return _ds[tenant]


def drop_tenant(tenant: str) -> None:
    with _lock:
        _fw.pop(tenant, None)
        _ds.pop(tenant, None)
    for k in ("files", "studio"):
        shutil.rmtree(_root(tenant, k), ignore_errors=True)


def _fwerr(e: FileWorkerError):
    status = 404 if e.code in ("UNKNOWN_OP", "UNKNOWN_PLAN") else 409 if e.code in ("ALREADY_UNDONE", "PLAN_NOT_APPLICABLE", "DESTINATION_OCCUPIED", "OVERWRITE_REFUSED", "VERIFY_FAILED") else 422
    return err(status, e.code.lower(), str(e))


def _doc_err(e: DocumentError):
    return err(getattr(e, "status_code", 400), "document_error", str(e))


# ---------------------------------------------------------------- files
@router.get("/files")
def inventory(ctx: Ctx = Depends(current_ctx)):
    try:
        return {**fw(ctx.tenant_id).inventory(), "scope": "Your private sandbox. REDEEM's file worker cannot see anything outside it; symlinks are never followed."}
    except FileWorkerError as e:
        raise _fwerr(e)


@router.post("/files/upload", status_code=201)
async def upload_file(file: UploadFile = File(...), ctx: Ctx = Depends(current_ctx)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise err(413, "file_too_large", "Max 20 MB")
    name = re.sub(r"\.{2,}", ".", re.sub(r"[^\w.\- ]", "_", (file.filename or "upload")))[-120:].lstrip(".") or "upload"
    w = fw(ctx.tenant_id)
    try:
        dst = w._resolve(f"inbox/{name}")
        os.makedirs(dst.parent, exist_ok=True)
        if os.path.lexists(dst):
            stem, dot, ext = name.rpartition(".")
            name = f"{stem or name}-{os.urandom(3).hex()}{dot}{ext}" if dot else f"{name}-{os.urandom(3).hex()}"
            dst = w._resolve(f"inbox/{name}")
        w._write_exclusive(dst, [data])
    except FileWorkerError as e:
        raise _fwerr(e)
    audit(ctx.db, ctx, "files.upload", name)
    ctx.db.commit()
    return {"path": f"inbox/{name}", "size": len(data)}


@router.get("/files/duplicates")
def duplicates(ctx: Ctx = Depends(current_ctx)):
    try:
        return fw(ctx.tenant_id).duplicates()
    except FileWorkerError as e:
        raise _fwerr(e)


@router.post("/files/plan", status_code=201)
def plan(ctx: Ctx = Depends(current_ctx)):
    try:
        p = fw(ctx.tenant_id).plan_dedupe()
    except FileWorkerError as e:
        raise _fwerr(e)
    audit(ctx.db, ctx, "files.plan", p["plan_id"])
    ctx.db.commit()
    return {**p, "note": "Dry run: nothing has moved. Apply re-checks every file's hash first and refuses a stale plan."}


@router.post("/files/apply")
def apply_plan(body: ApplyPlanIn, ctx: Ctx = Depends(current_ctx)):
    try:
        r = fw(ctx.tenant_id).apply(body.plan_id)
    except FileWorkerError as e:
        raise _fwerr(e)
    audit(ctx.db, ctx, "files.apply", body.plan_id)
    ctx.db.commit()
    if r["verification"]["status"] == "STALE_PLAN":   # temporal guard fired: a file changed after the dry run; nothing was moved
        raise err(409, "plan_stale", "A file changed after you reviewed the plan, so nothing was moved. Create a new plan.", checks=r["verification"]["checks"])
    return r


@router.post("/files/undo")
def undo_op(body: UndoIn, ctx: Ctx = Depends(current_ctx)):
    try:
        r = fw(ctx.tenant_id).undo(body.op_id)
    except FileWorkerError as e:
        raise _fwerr(e)
    audit(ctx.db, ctx, "files.undo", body.op_id)
    ctx.db.commit()
    return r


@router.get("/files/operations")
def operations(ctx: Ctx = Depends(current_ctx)):
    w = fw(ctx.tenant_id)
    with closing(sqlite3.connect(str(w.db_path), timeout=10)) as con:
        con.row_factory = sqlite3.Row
        ops = [dict(r) for r in con.execute("SELECT op_id, kind, plan_id, status, created_at, updated_at, verification_json FROM fw_ops WHERE sandbox=? ORDER BY created_at DESC LIMIT 50", (str(w.root),))]
        plans = [dict(r) for r in con.execute("SELECT plan_id, created_at, status, moves_json FROM fw_plans WHERE sandbox=? ORDER BY created_at DESC LIMIT 50", (str(w.root),))]
    for o in ops:
        o["verification"] = json.loads(o.pop("verification_json") or "null")
    for p in plans:
        p["moves"] = json.loads(p.pop("moves_json"))
    return {"operations": ops, "plans": plans}


@router.get("/files/download")
def download_file(path: str = Query(..., max_length=300), ctx: Ctx = Depends(current_ctx)):
    w = fw(ctx.tenant_id)
    try:
        p = w._resolve(path)
    except FileWorkerError as e:
        raise _fwerr(e)
    if not p.is_file():
        raise err(404, "not_found", "No such file")
    return Response(p.read_bytes(), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{p.name}"', "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- PDF studio


@router.get("/studio/documents")
def studio_list(ctx: Ctx = Depends(current_ctx)):
    return {"items": ds(ctx.tenant_id).list_documents(ctx.user.id, ctx.workspace_id)}


@router.post("/studio/import", status_code=201)
async def studio_import(file: UploadFile = File(...), ctx: Ctx = Depends(current_ctx)):
    data = await file.read(MAX_UPLOAD + 1)
    try:
        d = ds(ctx.tenant_id).import_pdf(ctx.user.id, ctx.workspace_id, data, re.sub(r"[^\w.\- ]", "_", file.filename or "upload.pdf")[:120])
    except DocumentError as e:
        raise _doc_err(e)
    audit(ctx.db, ctx, "studio.import", d["id"])
    ctx.db.commit()
    return d


@router.post("/studio/transform", status_code=201)
def studio_transform(body: TransformIn, ctx: Ctx = Depends(current_ctx)):
    try:
        d = ds(ctx.tenant_id).transform(ctx.user.id, ctx.workspace_id, body.operation, body.document_ids, body.expected_sha256, body.degrees, body.pages)
    except DocumentError as e:
        raise _doc_err(e)
    audit(ctx.db, ctx, "studio.transform", d["id"], {"op": body.operation})
    ctx.db.commit()
    return d


@router.post("/studio/report", status_code=201)
def studio_report(body: ReportIn, ctx: Ctx = Depends(current_ctx)):
    try:
        d = ds(ctx.tenant_id).create_report(ctx.user.id, ctx.workspace_id, body.title, body.text)
    except DocumentError as e:
        raise _doc_err(e)
    audit(ctx.db, ctx, "studio.report", d["id"])
    ctx.db.commit()
    return d


@router.get("/studio/documents/{doc_id}/download")
def studio_download(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    try:
        d = ds(ctx.tenant_id).get_document(ctx.user.id, ctx.workspace_id, doc_id)
        data = ds(ctx.tenant_id).read_pdf(ctx.user.id, ctx.workspace_id, doc_id)
    except DocumentError as e:
        raise _doc_err(e)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{d["name"]}"', "X-Content-Type-Options": "nosniff"})


@router.get("/studio/documents/{doc_id}/text")
def studio_text(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    try:
        return {"text": ds(ctx.tenant_id).extract_text(ctx.user.id, ctx.workspace_id, doc_id)}
    except DocumentError as e:
        raise _doc_err(e)


@router.delete("/studio/documents/{doc_id}", status_code=204)
def studio_delete(doc_id: str, ctx: Ctx = Depends(current_ctx)):
    try:
        ok = ds(ctx.tenant_id).delete_document(ctx.user.id, ctx.workspace_id, doc_id)
    except DocumentError as e:
        raise _doc_err(e)
    if not ok:
        raise err(404, "not_found", "Document not found")
    audit(ctx.db, ctx, "studio.delete", doc_id)
    ctx.db.commit()
