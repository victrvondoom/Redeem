from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app.config import settings
from app.security import vault

B = "/api/v1"
SECRET = "Booking FA2041 refund of Rs 8450 for passenger Asha Rao, invoice INV-77231"


def _upload(api, name="receipt.txt"):
    r = api.post(f"{B}/documents", files={"file": (name, SECRET.encode(), "text/plain")})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_document_text_and_bytes_are_encrypted_at_rest_but_served_to_owner(api, db):
    d = _upload(api)
    did = d["id"]
    raw = db.execute(text("select text_content from documents where id=:i"), {"i": did}).scalar()
    assert raw.startswith("enc1:") and "Asha" not in raw and "INV-77231" not in raw
    blob = Path(db.execute(text("select blob_path from documents where id=:i"), {"i": did}).scalar()).read_bytes()
    assert blob.startswith(vault.MAGIC) and b"Asha" not in blob
    assert api.get(f"{B}/documents/{did}/download").content.decode() == SECRET
    assert "INV-77231" in api.get(f"{B}/documents/{did}").json()["text"]
    assert api.get(f"{B}/documents?q=INV-77231").json()["total"] == 1  # search still works on decrypted text


def test_other_tenant_cannot_read_and_blob_is_bound_to_its_tenant(api, api2, db):
    did = _upload(api)["id"]
    assert api2.get(f"{B}/documents/{did}").status_code == 404
    assert api2.get(f"{B}/documents/{did}/download").status_code == 404
    path = db.execute(text("select blob_path from documents where id=:i"), {"i": did}).scalar()
    with pytest.raises(InvalidTag):
        vault.read_blob(path, "ten_someone_else")


def test_master_key_file_is_private():
    vault._master_key()
    p = Path(settings.data_dir) / ".master_key"
    assert not p.exists() or (p.stat().st_mode & 0o077) == 0


def test_public_stats_are_aggregate_only_and_unauthenticated(api):
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app).get(f"{B}/public/stats")
    assert r.status_code == 200
    j = r.json()
    assert {"verified_claims", "ledger_events", "missions", "knowledge_passages"} <= set(j)
    assert "email" not in r.text and "tenant" not in r.text.replace("this deployment only", "")


def test_health_reports_database_dialect(api):
    from fastapi.testclient import TestClient
    from app.main import app
    j = TestClient(app).get(f"{B}/health").json()
    assert j["db"] == "ok" and j["dialect"] in ("sqlite", "postgresql")
