import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

B = "/api/v1"


def up(api, name, data):
    r = api.post(f"{B}/files/upload", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["path"]


def pdf(pages: int, label: str = "Page") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(pages):
        c.drawString(72, 750, f"{label} {i + 1} of {pages}")
        c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- file worker (inherited from RESOLVE)
def test_dedupe_dry_run_apply_verify_and_undo(api):
    a, _b, _c = up(api, "a.txt", b"same bytes"), up(api, "b.txt", b"same bytes"), up(api, "c.txt", b"different")
    inv = api.get(f"{B}/files").json()
    assert inv["total_files"] == 3 and "private sandbox" in inv["scope"]
    assert len(api.get(f"{B}/files/duplicates").json()["groups"]) == 1
    plan = api.post(f"{B}/files/plan").json()
    assert plan["dry_run"] is True and len(plan["moves"]) == 1 and "nothing has moved" in plan["note"]
    assert api.get(f"{B}/files").json()["total_files"] == 3                                   # dry run really changed nothing
    done = api.post(f"{B}/files/apply", {"plan_id": plan["plan_id"]}).json()
    assert done["verification"]["status"] == "CONFIRMED" and all(c["origin_absent"] and c["ok"] for c in done["verification"]["checks"])
    assert api.get(f"{B}/files").json()["total_files"] == 2
    ops = api.get(f"{B}/files/operations").json()
    assert ops["operations"][0]["status"] == "CONFIRMED" and ops["operations"][0]["verification"]["status"] == "CONFIRMED"
    undo = api.post(f"{B}/files/undo", {"op_id": done["op_id"]}).json()
    assert undo["verification"]["status"] == "CONFIRMED" and undo["restored"]
    assert api.get(f"{B}/files").json()["total_files"] == 3                                   # restored
    assert api.get(f"{B}/files/download?path={a}").content == b"same bytes"
    again = api.post(f"{B}/files/undo", {"op_id": done["op_id"]})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_undone"


def test_stale_plan_is_refused_when_a_file_changes_after_review(api):
    up(api, "a.txt", b"same"), up(api, "b.txt", b"same")
    plan = api.post(f"{B}/files/plan").json()
    from app.api import workspace
    from conftest import SessionLocal  # noqa: F401
    w = workspace.fw(api.me["tenant_id"])
    victim = w.root / plan["moves"][0]["src"]
    victim.write_bytes(b"EDITED after the plan was reviewed")
    r = api.post(f"{B}/files/apply", {"plan_id": plan["plan_id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "plan_stale"
    assert any(c["current_sha256"] != c["planned_sha256"] for c in r.json()["error"]["checks"])
    assert victim.read_bytes() == b"EDITED after the plan was reviewed"                      # the changed file was NOT quarantined


def test_paths_cannot_escape_the_sandbox(api):
    for bad in ("../../etc/passwd", "/etc/passwd", "inbox/../../x", "..%2f..%2fetc%2fpasswd"):
        r = api.get(f"{B}/files/download", params={"path": bad})
        assert r.status_code in (404, 422), bad
    up(api, "../../evil.txt", b"x")                                                           # hostile filename is neutralised, stays inside the sandbox
    paths = [f["path"] for f in api.get(f"{B}/files").json()["files"]]
    assert paths and all(p.startswith("inbox/") and ".." not in p for p in paths)


def test_file_sandboxes_are_tenant_private(api, api2):
    up(api, "secret.txt", b"tenant A only")
    plan = api.post(f"{B}/files/plan").json()
    assert api2.get(f"{B}/files").json()["total_files"] == 0
    assert api2.get(f"{B}/files/download", params={"path": "inbox/secret.txt"}).status_code in (404, 422)
    assert api2.post(f"{B}/files/apply", {"plan_id": plan["plan_id"]}).status_code == 404
    assert api2.post(f"{B}/files/undo", {"op_id": "op_000000000000"}).status_code == 404


# ---------------------------------------------------------------- PDF studio (inherited from RESOLVE)
def test_pdf_studio_import_transform_with_source_hash_guard_and_verification(api):
    d1 = api.post(f"{B}/studio/import", files={"file": ("one.pdf", pdf(3), "application/pdf")}).json()
    d2 = api.post(f"{B}/studio/import", files={"file": ("two.pdf", pdf(2, "Other"), "application/pdf")}).json()
    sha = {d1["id"]: d1["sha256"], d2["id"]: d2["sha256"]}
    merged = api.post(f"{B}/studio/transform", {"operation": "merge", "document_ids": [d1["id"], d2["id"]], "expected_sha256": sha}).json()
    got = PdfReader(io.BytesIO(api.get(f"{B}/studio/documents/{merged['id']}/download").content))
    assert len(got.pages) == 5 and merged["operation"] == "merge"                              # real merged PDF, read back
    trimmed = api.post(f"{B}/studio/transform", {"operation": "delete_pages", "document_ids": [merged["id"]], "expected_sha256": {merged["id"]: merged["sha256"]}, "pages": [1, 2]}).json()
    assert len(PdfReader(io.BytesIO(api.get(f"{B}/studio/documents/{trimmed['id']}/download").content)).pages) == 3
    rot = api.post(f"{B}/studio/transform", {"operation": "rotate", "document_ids": [d1["id"]], "expected_sha256": {d1["id"]: d1["sha256"]}, "degrees": 90, "pages": [1]}).json()
    assert PdfReader(io.BytesIO(api.get(f"{B}/studio/documents/{rot['id']}/download").content)).pages[0].get("/Rotate") == 90
    stale = api.post(f"{B}/studio/transform", {"operation": "rotate", "document_ids": [d1["id"]], "expected_sha256": {d1["id"]: "0" * 64}, "degrees": 90})
    assert stale.status_code == 409                                                           # version guard: the PDF the user reviewed must be the one transformed
    assert "Page 1 of 3" in api.get(f"{B}/studio/documents/{d1['id']}/text").json()["text"]
    assert api.post(f"{B}/studio/transform", {"operation": "delete_pages", "document_ids": [d1["id"]], "expected_sha256": {d1["id"]: d1["sha256"]}, "pages": [1, 2, 3]}).status_code == 400
    assert len(api.get(f"{B}/studio/documents").json()["items"]) == 5


def test_pdf_studio_report_creation_rejects_non_pdfs_and_is_tenant_scoped(api, api2):
    rep = api.post(f"{B}/studio/report", {"title": "Q3 summary", "text": "Line one.\n\nLine two of the report."}).json()
    assert api.get(f"{B}/studio/documents/{rep['id']}/download").content.startswith(b"%PDF-")
    bad = api.post(f"{B}/studio/import", files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")})
    assert bad.status_code == 400
    assert api2.get(f"{B}/studio/documents").json()["items"] == []
    assert api2.get(f"{B}/studio/documents/{rep['id']}/download").status_code in (400, 404)
    assert api2.delete(f"{B}/studio/documents/{rep['id']}").status_code in (400, 404)
    assert api.delete(f"{B}/studio/documents/{rep['id']}").status_code == 204
    assert api.get(f"{B}/studio/documents/{rep['id']}/download").status_code in (400, 404)


def test_account_deletion_removes_files_studio_and_browser_data(api):
    from pathlib import Path
    from app.config import settings
    up(api, "x.txt", b"data")
    api.post(f"{B}/studio/report", {"title": "T", "text": "hello world"})
    t = api.me["tenant_id"]
    roots = [Path(settings.data_dir) / k / t for k in ("files", "studio")]
    assert all(r.exists() for r in roots)
    assert api.delete(f"{B}/users/me").status_code == 204
    assert not any(r.exists() for r in roots)
