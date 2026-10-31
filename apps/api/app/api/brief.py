from fastapi import APIRouter, Depends

from ..core.deps import Ctx, audit, current_ctx, err
from ..reclaim import docintel
from ..resolve import brief
from ..schemas import BriefExtractIn, BriefRenderIn

router = APIRouter(prefix="/api/v1/studio/brief", tags=["studio"])


@router.post("/extract")
def extract(body: BriefExtractIn, ctx: Ctx = Depends(current_ctx)):
    return brief.extract(body.brief)


@router.post("/render", status_code=201)
def render(body: BriefRenderIn, ctx: Ctx = Depends(current_ctx)):
    s = body.structured.model_dump()
    if not s["sections"] and not s["action_items"]:
        raise err(422, "empty_brief", "Nothing to render")
    pdf = brief.render(s, ctx.user.name)
    d, info = docintel.ingest(ctx.db, ctx.tenant_id, f"{s['title'][:60].strip() or 'brief'}.pdf", "application/pdf", pdf, body.domain)
    d.extracted = {**d.extracted, "provenance": {"generator": "brief_to_pdf", "source_sha256": s["source_sha256"], "edited_before_render": True}}
    audit(ctx.db, ctx, "brief.render", d.id)
    ctx.db.commit()
    return {"document_id": d.id, "filename": d.filename, "pages": d.page_count, "size": d.size, "sha256": d.sha256, "duplicate": bool(info.get("duplicate")),
            "download": f"/api/v1/documents/{d.id}/download", "text_preview": (d.text_content or "")[:600]}
