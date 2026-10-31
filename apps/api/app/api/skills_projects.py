"""Recorded browser skills (record-by-doing, replay, live run control) and the Project Store."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..core.deps import Ctx, audit, current_ctx, err
from ..db import utcnow
from ..models import BrowserSkill, BrowserSkillRun, BrowserSnapshot, Case, Document, Mission, Project, ProjectItem
from ..resolve import browser as rb
from ..resolve import skills as sk

router = APIRouter(prefix="/api/v1", tags=["skills", "projects"])


class RecordIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    steps: list[dict] = Field(min_length=1, max_length=25)
    params: dict[str, str] = Field(default_factory=dict)


class RunIn(BaseModel):
    params: dict[str, str] = Field(default_factory=dict)
    background: bool = True


class ControlIn(BaseModel):
    action: str = Field(pattern="^(pause|resume|stop)$")


def _skill_json(s: BrowserSkill) -> dict:
    return {"id": s.id, "name": s.name, "steps": s.steps, "params": s.params, "runs": s.runs, "last_status": s.last_status,
            "recorded_session_id": s.recorded_session_id, "created_at": s.created_at.isoformat()}


def _run_json(ctx: Ctx, r: BrowserSkillRun) -> dict:
    snaps = list(ctx.db.scalars(select(BrowserSnapshot).where(BrowserSnapshot.tenant_id == ctx.tenant_id, BrowserSnapshot.session_id == (r.session_id or "")).order_by(BrowserSnapshot.created_at)))
    return {"id": r.id, "skill_id": r.skill_id, "session_id": r.session_id, "status": r.status, "step_index": r.step_index, "total_steps": r.total_steps,
            "error": r.error, "uncertain": r.uncertain, "updated_at": r.updated_at.isoformat(),
            "frames": [{"id": x.id, "phase": x.phase, "label": x.label, "url": x.url, "title": x.title, "screenshot_sha": x.screenshot_sha,
                        "screenshot_url": f"/api/v1/browser/snapshots/{x.id}/screenshot", "at": x.created_at.isoformat()} for x in snaps]}


def _need_browser():
    ok, why = rb.browser_available()
    if not ok:
        raise err(503, "browser_unavailable", why)


def _skill(ctx: Ctx, sid: str) -> BrowserSkill:
    s = ctx.db.scalar(select(BrowserSkill).where(BrowserSkill.id == sid, BrowserSkill.tenant_id == ctx.tenant_id))
    if not s:
        raise err(404, "not_found", "Skill not found")
    return s


@router.get("/browser/skills")
def list_skills(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(BrowserSkill).where(BrowserSkill.tenant_id == ctx.tenant_id).order_by(BrowserSkill.created_at.desc()))
    return {"items": [_skill_json(s) for s in rows], "apps": sorted(sk.APPS), "ops": sorted(sk.OPS)}


@router.post("/browser/skills/record", status_code=201)
def record_skill(body: RecordIn, ctx: Ctx = Depends(current_ctx)):
    """Record by doing: run the steps once in a real browser; save the skill only if every step succeeded."""
    try:
        steps, params = sk.validate_steps(body.steps)
        for p in params:
            sk.substitute("{{%s}}" % p, body.params)
    except sk.SkillError as e:
        raise err(422, "invalid_skill", str(e))
    _need_browser()
    run = BrowserSkillRun(tenant_id=ctx.tenant_id)
    ctx.db.add(run)
    ctx.db.commit()
    sk.execute(ctx.db, run, steps, body.params)
    saved = None
    if run.status == "DONE":
        s = BrowserSkill(tenant_id=ctx.tenant_id, name=body.name.strip(), steps=steps, params=params, recorded_session_id=run.session_id, runs=1, last_status="DONE")
        ctx.db.add(s)
        ctx.db.flush()
        run.skill_id = s.id
        audit(ctx.db, ctx, "skill.record", s.id)
        ctx.db.commit()
        saved = _skill_json(s)
    return {"skill": saved, "recording": _run_json(ctx, run)}


@router.get("/browser/skills/{skill_id}")
def get_skill(skill_id: str, ctx: Ctx = Depends(current_ctx)):
    s = _skill(ctx, skill_id)
    runs = ctx.db.scalars(select(BrowserSkillRun).where(BrowserSkillRun.tenant_id == ctx.tenant_id, BrowserSkillRun.skill_id == s.id).order_by(BrowserSkillRun.created_at.desc()).limit(20))
    return {**_skill_json(s), "history": [{"id": r.id, "status": r.status, "step_index": r.step_index, "total_steps": r.total_steps, "error": r.error,
                                           "uncertain": r.uncertain, "at": r.created_at.isoformat()} for r in runs]}


@router.delete("/browser/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: str, ctx: Ctx = Depends(current_ctx)):
    s = _skill(ctx, skill_id)
    ctx.db.delete(s)
    audit(ctx.db, ctx, "skill.delete", skill_id)
    ctx.db.commit()


@router.post("/browser/skills/{skill_id}/run", status_code=202)
def run_skill(skill_id: str, body: RunIn, ctx: Ctx = Depends(current_ctx)):
    s = _skill(ctx, skill_id)
    try:
        for p in s.params:
            sk.substitute("{{%s}}" % p, body.params)
    except sk.SkillError as e:
        raise err(422, "missing_parameter", str(e))
    _need_browser()
    busy = ctx.db.scalar(select(BrowserSkillRun).where(BrowserSkillRun.tenant_id == ctx.tenant_id, BrowserSkillRun.status.in_(["QUEUED", "RUNNING", "PAUSED"])))
    if busy:
        raise err(409, "run_in_progress", "Another browser run is still in progress. Stop it or wait for it to finish.")
    run = BrowserSkillRun(tenant_id=ctx.tenant_id, skill_id=s.id, total_steps=len(s.steps))
    ctx.db.add(run)
    audit(ctx.db, ctx, "skill.run", s.id)
    ctx.db.commit()
    if body.background:
        sk.execute_in_background(run.id, list(s.steps), dict(body.params))
    else:
        sk.execute(ctx.db, run, list(s.steps), dict(body.params))
    return _run_json(ctx, run)


@router.get("/browser/skill-runs/{run_id}")
def get_run(run_id: str, ctx: Ctx = Depends(current_ctx)):
    r = ctx.db.scalar(select(BrowserSkillRun).where(BrowserSkillRun.id == run_id, BrowserSkillRun.tenant_id == ctx.tenant_id))
    if not r:
        raise err(404, "not_found", "Run not found")
    ctx.db.refresh(r)
    return _run_json(ctx, r)


@router.post("/browser/skill-runs/{run_id}/control")
def control_run(run_id: str, body: ControlIn, ctx: Ctx = Depends(current_ctx)):
    r = ctx.db.scalar(select(BrowserSkillRun).where(BrowserSkillRun.id == run_id, BrowserSkillRun.tenant_id == ctx.tenant_id))
    if not r:
        raise err(404, "not_found", "Run not found")
    if r.status not in ("QUEUED", "RUNNING", "PAUSED"):
        raise err(409, "not_running", f"Run is {r.status}")
    sk.control(r.id, body.action)
    audit(ctx.db, ctx, f"skill_run.{body.action}", r.id)
    ctx.db.commit()
    return {"id": r.id, "requested": body.action}


# ---------------------------------------------------------------- Project Store
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ItemIn(BaseModel):
    kind: str = Field(pattern="^(mission|case|document)$")
    ref_id: str = Field(min_length=3, max_length=40)


_KIND = {"mission": Mission, "case": Case, "document": Document}


def _project(ctx: Ctx, pid: str) -> Project:
    p = ctx.db.scalar(select(Project).where(Project.id == pid, Project.tenant_id == ctx.tenant_id))
    if not p:
        raise err(404, "not_found", "Project not found")
    return p


def _describe(ctx: Ctx, it: ProjectItem) -> dict:
    m = _KIND[it.kind]
    o = ctx.db.scalar(select(m).where(m.id == it.ref_id, m.tenant_id == ctx.tenant_id))
    base = {"id": it.id, "kind": it.kind, "ref_id": it.ref_id, "added_at": it.created_at.isoformat(), "missing": o is None}
    if o is None:
        return base
    if it.kind == "mission":
        return {**base, "title": o.intent[:140], "status": o.status, "href": f"/app/missions/{o.id}"}
    if it.kind == "case":
        return {**base, "title": o.title, "status": getattr(o, "status", None), "href": f"/app/cases/{o.id}"}
    return {**base, "title": o.filename, "status": None, "href": "/app/evidence"}


@router.get("/projects")
def list_projects(ctx: Ctx = Depends(current_ctx), q: str | None = Query(None, max_length=80)):
    stmt = select(Project).where(Project.tenant_id == ctx.tenant_id)
    if q:
        stmt = stmt.where(Project.name.ilike(f"%{q}%"))
    ps = list(ctx.db.scalars(stmt.order_by(Project.updated_at.desc())))
    counts: dict[str, int] = {}
    for it in ctx.db.scalars(select(ProjectItem).where(ProjectItem.tenant_id == ctx.tenant_id)):
        counts[it.project_id] = counts.get(it.project_id, 0) + 1
    return {"items": [{"id": p.id, "name": p.name, "description": p.description, "items": counts.get(p.id, 0), "updated_at": p.updated_at.isoformat()} for p in ps]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, ctx: Ctx = Depends(current_ctx)):
    p = Project(tenant_id=ctx.tenant_id, name=body.name.strip(), description=body.description.strip())
    ctx.db.add(p)
    ctx.db.flush()
    audit(ctx.db, ctx, "project.create", p.id)
    ctx.db.commit()
    return {"id": p.id, "name": p.name, "description": p.description, "items": []}


@router.get("/projects/{pid}")
def get_project(pid: str, ctx: Ctx = Depends(current_ctx)):
    p = _project(ctx, pid)
    items = ctx.db.scalars(select(ProjectItem).where(ProjectItem.project_id == p.id, ProjectItem.tenant_id == ctx.tenant_id).order_by(ProjectItem.created_at))
    return {"id": p.id, "name": p.name, "description": p.description, "updated_at": p.updated_at.isoformat(), "items": [_describe(ctx, i) for i in items]}


@router.patch("/projects/{pid}")
def update_project(pid: str, body: ProjectIn, ctx: Ctx = Depends(current_ctx)):
    p = _project(ctx, pid)
    p.name, p.description = body.name.strip(), body.description.strip()
    audit(ctx.db, ctx, "project.update", p.id)
    ctx.db.commit()
    return {"id": p.id, "name": p.name, "description": p.description}


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, ctx: Ctx = Depends(current_ctx)):
    p = _project(ctx, pid)
    ctx.db.execute(delete(ProjectItem).where(ProjectItem.project_id == p.id, ProjectItem.tenant_id == ctx.tenant_id))
    ctx.db.delete(p)
    audit(ctx.db, ctx, "project.delete", pid)
    ctx.db.commit()


@router.post("/projects/{pid}/items", status_code=201)
def add_item(pid: str, body: ItemIn, ctx: Ctx = Depends(current_ctx)):
    p = _project(ctx, pid)
    m = _KIND[body.kind]
    if not ctx.db.scalar(select(m.id).where(m.id == body.ref_id, m.tenant_id == ctx.tenant_id)):
        raise err(404, "not_found", f"No {body.kind} with that id")
    if ctx.db.scalar(select(ProjectItem).where(ProjectItem.project_id == p.id, ProjectItem.kind == body.kind, ProjectItem.ref_id == body.ref_id)):
        raise err(409, "duplicate", "Already in this project")
    it = ProjectItem(tenant_id=ctx.tenant_id, project_id=p.id, kind=body.kind, ref_id=body.ref_id)
    ctx.db.add(it)
    p.updated_at = it.created_at = utcnow()
    audit(ctx.db, ctx, "project.add_item", p.id)
    ctx.db.commit()
    return _describe(ctx, it)


@router.delete("/projects/{pid}/items/{item_id}", status_code=204)
def remove_item(pid: str, item_id: str, ctx: Ctx = Depends(current_ctx)):
    p = _project(ctx, pid)
    it = ctx.db.scalar(select(ProjectItem).where(ProjectItem.id == item_id, ProjectItem.project_id == p.id, ProjectItem.tenant_id == ctx.tenant_id))
    if not it:
        raise err(404, "not_found", "Item not found")
    ctx.db.delete(it)
    ctx.db.commit()
