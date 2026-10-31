import httpx
import pytest
from sqlalchemy import select, text

from app.config import settings
from app.memory import extract
from app.models import Call, EncryptionKey, MemoryItem
from app.security import vault
from app.voice import bolna

B = "/api/v1"


def ingest(api, utterance, field=None, **kw):
    r = api.post(f"{B}/memory/ingest", {"utterance": utterance, "expected_field": field, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- mapping
def test_spoken_answer_maps_to_the_asked_field_and_normalises_the_value():
    r = extract.map_answer("Window please, I always take the window", "travel.seat_preference")
    assert [(c["field"], c["value"]) for c in r["candidates"]] == [("travel.seat_preference", "window")]
    r = extract.map_answer("मैं शाकाहारी खाना लेता हूँ", "travel.meal_preference")
    assert r["candidates"][0]["value"] == "vegetarian"
    r = extract.map_answer("ஜன்னல் இருக்கை", "travel.seat_preference")
    assert r["candidates"][0]["value"] == "window"


def test_negation_ambiguity_and_unmapped_ask_for_clarification_instead_of_guessing():
    assert extract.map_answer("not window, aisle", "travel.seat_preference")["candidates"][0]["value"] == "aisle"
    amb = extract.map_answer("window or aisle, either", "travel.seat_preference")
    assert amb["ambiguous"] and not amb["candidates"] and "window and aisle" in amb["clarification"]
    un = extract.map_answer("whatever is fine", "travel.seat_preference")
    assert un["unmapped"] and "seat" in un["clarification"]
    assert extract.map_answer("I am Asha", "no.such.field").get("error") == "unknown_field"


def test_free_speech_can_fill_several_fields_and_sensitive_ones_need_confirmation(api):
    r = ingest(api, "Mujhe whatsapp pe contact karo, aur mera number 98765 43210 hai", fixture=True)
    fields = {s["field"]: s for s in r["saved"]}
    assert fields["profile.contact_method"]["status"] == "confirmed" or fields["profile.contact_method"]["status"] == "proposed"
    assert fields["profile.phone"]["status"] == "proposed" and fields["profile.phone"]["value"] == "9876543210"
    assert fields["profile.phone"]["id"] in r["needs_confirmation"]


# ---------------------------------------------------------------- persistence, encryption, provenance
def test_memory_is_encrypted_in_the_database_and_carries_provenance(api, db):
    r = ingest(api, "I prefer the window seat", "travel.seat_preference", fixture=True)
    item = r["saved"][0]
    assert item["status"] == "confirmed" and item["simulated"] is True and item["source_kind"] == "bolna_fixture" and item["explicit"] and item["confidence"] >= 0.85
    raw = db.execute(text("select value_enc, quote_enc from memory_items where id=:i"), {"i": item["id"]}).one()
    assert raw[0].startswith("enc2t:") and "window" not in raw[0] and "window" not in raw[1]
    again = api.get(f"{B}/memory").json()["items"][0]
    assert again["value"] == "window" and again["quote"] and again["source_kind"] == "bolna_fixture"


def test_call_sourced_memory_requires_consent_and_an_owned_call(api, api2, db):
    cid = make_call(api, "user: I would like an aisle seat\nassistant: Noted\nuser: my email is asha@example.com")
    assert api.post(f"{B}/memory/from-call/{cid}").json()["error"]["code"] == "consent_required"
    assert api.post(f"{B}/memory/ingest", {"utterance": "aisle", "call_id": cid}).status_code == 403
    api.post(f"{B}/memory/consent?granted=true")
    saved = api.post(f"{B}/memory/from-call/{cid}").json()["saved"]
    by = {s["field"]: s for s in saved}
    assert by["travel.seat_preference"]["source_kind"] == "bolna_call" and by["travel.seat_preference"]["source_ref"] == cid and by["travel.seat_preference"]["segment"] == "0"
    assert by["profile.email"]["status"] == "proposed"
    api2.post(f"{B}/memory/consent?granted=true")
    assert api2.post(f"{B}/memory/from-call/{cid}").status_code == 404      # someone else's call
    assert api2.post(f"{B}/memory/ingest", {"utterance": "aisle", "call_id": cid}).status_code == 404


def make_call(api, transcript):
    settings.bolna_api_key, settings.bolna_agent_id, settings.bolna_webhook_secret = "bn-test-KEY", "agent-1", "whsec-test"
    orig = bolna.make_client
    bolna.make_client = lambda: bolna.BolnaClient("https://api.bolna.test", "bn-test-KEY", "agent-1", 2.0, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"sip": 1})))
    try:
        api.post(f"{B}/voice/consent", {"purpose": "voice_call", "granted": True})
        cid = api.post(f"{B}/voice/session").headers["x-redeem-call-id"]
        api.post(f"{B}/voice/calls/{cid}/attach", {"execution_id": "exec-m1"})
    finally:
        bolna.make_client = orig
    from app.db import SessionLocal
    with SessionLocal() as s:
        s.get(Call, cid).transcript = transcript
        s.commit()
    return cid


# ---------------------------------------------------------------- review, correction, deletion, use in missions
def test_proposals_are_not_used_until_confirmed_then_prefill_a_later_mission(api):
    sens = ingest(api, "my number is 9876543210", "profile.phone")["saved"][0]
    seat = ingest(api, "window seat", "travel.seat_preference", fixture=True)["saved"][0]
    m = api.post(f"{B}/missions", {"intent": "My flight FA2041 was cancelled, I need a refund", "language": "en", "source": "text"}).json()
    used = {u["field"] for u in m["memory_used"]}
    assert "travel.seat_preference" in used and "profile.phone" not in used            # proposal never used
    ev = api.get(f"{B}/missions/{m['id']}/events").json()["items"]
    mu = next(e for e in ev if e["type"] == "MEMORY_USED")
    assert "window" not in str(mu["data"])                                               # values are not copied into the ledger
    api.post(f"{B}/memory/{sens['id']}/confirm")
    assert api.get(f"{B}/memory/relevant?intent=flight refund").json()["items"]
    assert seat["id"]


def test_correct_reject_pin_delete_and_category_delete(api):
    a = ingest(api, "window", "travel.seat_preference")["saved"][0]
    fixed = api.post(f"{B}/memory/{a['id']}/confirm", {"value": "aisle"}).json()
    assert fixed["value"] == "aisle" and fixed["source_kind"] == "typed" and fixed["confidence"] == 1.0
    assert api.patch(f"{B}/memory/{a['id']}", {"pinned": True}).json()["pinned"] is True
    b = ingest(api, "vegetarian", "travel.meal_preference")["saved"][0]
    assert api.post(f"{B}/memory/{b['id']}/reject").json()["status"] == "rejected"
    assert api.delete(f"{B}/memory/{a['id']}").status_code == 204
    ingest(api, "jain", "travel.meal_preference")
    assert api.delete(f"{B}/memory?category=travel").json()["deleted"] >= 1
    assert api.get(f"{B}/memory").json()["items"] == []


def test_new_confirmed_value_supersedes_the_old_one(api):
    ingest(api, "window", "travel.seat_preference")
    ingest(api, "aisle", "travel.seat_preference")
    items = api.get(f"{B}/memory?category=travel").json()["items"]
    assert [i["value"] for i in items] == ["aisle"]


def test_retention_expiry_purges_memory(api, db):
    r = ingest(api, "window", "travel.seat_preference", retention_days=30)["saved"][0]
    assert r["expires_at"]
    from datetime import timedelta
    from app.db import utcnow
    m = db.get(MemoryItem, r["id"])
    m.expires_at = utcnow() - timedelta(days=1)
    db.commit()
    assert api.get(f"{B}/memory").json()["items"] == []
    assert db.scalar(select(MemoryItem).where(MemoryItem.id == r["id"])) is None


def test_memory_idor_every_operation_is_blocked_across_tenants(api, api2):
    a = ingest(api, "window", "travel.seat_preference")["saved"][0]
    assert api2.get(f"{B}/memory").json()["items"] == []
    for call in (lambda: api2.post(f"{B}/memory/{a['id']}/confirm"), lambda: api2.post(f"{B}/memory/{a['id']}/reject"),
                 lambda: api2.patch(f"{B}/memory/{a['id']}", {"value": "x"}), lambda: api2.delete(f"{B}/memory/{a['id']}")):
        assert call().status_code == 404
    assert api2.get(f"{B}/memory/relevant?intent=flight").json()["items"] == []
    assert api.get(f"{B}/memory").json()["items"][0]["value"] == "window"


def test_export_and_account_deletion_cover_memory_and_destroy_the_keys(api, db):
    ingest(api, "window", "travel.seat_preference")
    exp = api.get(f"{B}/privacy/export").json()
    assert exp["memory"][0]["value"] == "window" and exp["encryption"]["algorithm"] == "AES-256-GCM" and exp["encryption"]["end_to_end"] is False
    tenant = db.scalar(select(MemoryItem.tenant_id))
    assert db.scalar(select(EncryptionKey).where(EncryptionKey.scope == tenant)) is not None
    assert api.delete(f"{B}/users/me").status_code == 204
    db.expire_all()
    assert db.scalar(select(MemoryItem)) is None and db.scalar(select(EncryptionKey).where(EncryptionKey.scope == tenant)) is None


def test_privacy_summary_reports_counts_and_encryption(api):
    ingest(api, "window", "travel.seat_preference")
    s = api.get(f"{B}/privacy/summary").json()
    assert s["counts"]["memory_items"] == 1 and s["encryption"]["kms_integrated"] is False and "ledger events" in " ".join(s["encryption"]["not_encrypted_at_application_layer"])


# ---------------------------------------------------------------- Bolna tools
def test_bolna_agent_tools_save_answer_and_recall_with_consent(api):
    cid = make_call(api, "")
    t = lambda name, body: api.c.post(f"{B}/voice/tools/{name}?token=whsec-test", json={"execution_id": "exec-m1", **body}).json()  # noqa: E731
    assert t("save_answer", {"utterance": "window", "field": "travel.seat_preference"})["saved"] is False       # no consent yet
    api.post(f"{B}/memory/consent?granted=true")
    r = t("save_answer", {"utterance": "window or aisle", "field": "travel.seat_preference"})
    assert r["saved"] == [] and "window and aisle" in r["ask_user"]
    r = t("save_answer", {"utterance": "window", "field": "travel.seat_preference", "segment": "3"})
    assert r["saved"] == ["travel.seat_preference"]
    assert t("recall", {"topic": "my flight"})["items"] == [{"field": "travel.seat_preference", "value": "window"}]
    assert api.get(f"{B}/memory").json()["items"][0]["source_ref"] == cid


# ---------------------------------------------------------------- vault (envelope encryption)
def test_dek_rotation_keeps_old_data_readable_and_new_writes_use_the_new_key(api, db):
    from app.db import SessionLocal
    a = api.post(f"{B}/documents", files={"file": ("a.txt", b"first document", "text/plain")}).json()["id"]
    r = api.post(f"{B}/privacy/keys/rotate").json()
    assert [k["status"] for k in r["key_versions"]] == ["retired", "active"] and r["key_versions"][-1]["version"] == 2
    b = api.post(f"{B}/documents", files={"file": ("b.txt", b"second document", "text/plain")}).json()["id"]
    assert api.get(f"{B}/documents/{a}/download").content == b"first document"
    assert api.get(f"{B}/documents/{b}/download").content == b"second document"
    with SessionLocal() as s:
        paths = dict(s.execute(text("select id, blob_path from documents")).all())
        from pathlib import Path
        ka = Path(paths[a]).read_bytes()[4:28].decode().strip()
        kb = Path(paths[b]).read_bytes()[4:28].decode().strip()
    assert ka != kb


def test_tampered_ciphertext_and_wrong_tenant_fail_closed(api, db):
    from cryptography.exceptions import InvalidTag
    blob = vault.encrypt_bytes(db, "ten_a", b"secret")
    assert vault.decrypt_bytes(db, "ten_a", blob) == b"secret"
    with pytest.raises(InvalidTag):
        vault.decrypt_bytes(db, "ten_a", blob[:-1] + bytes([blob[-1] ^ 1]))
    with pytest.raises(InvalidTag):
        vault.decrypt_bytes(db, "ten_b", blob)
    s = vault.encrypt_str(db, "ten_a", "hello")
    with pytest.raises(InvalidTag):
        vault.decrypt_str(db, "ten_b", s)


def test_kek_rotation_rewraps_deks_and_requires_the_previous_key(api, db, monkeypatch):
    import base64
    import secrets
    api.post(f"{B}/documents", files={"file": ("a.txt", b"kept", "text/plain")})
    old_kek = vault.current_kek_id()
    new = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    old_raw = base64.urlsafe_b64encode(vault._keks[old_kek]).decode()
    vault.reset_for_tests()
    monkeypatch.setenv("REDEEM_MASTER_KEY", new)
    with pytest.raises(vault.VaultError):               # without the previous key the old DEK cannot be unwrapped
        vault._dek_cache.clear()
        vault.rewrap_all(db)
    vault.reset_for_tests()
    monkeypatch.setenv("REDEEM_MASTER_KEY_PREVIOUS", old_raw)
    assert vault.rewrap_all(db) >= 1 and all(k.kek_id == vault.current_kek_id() for k in db.scalars(select(EncryptionKey)))
    db.commit()
    vault._dek_cache.clear()
    assert api.get(f"{B}/documents").json()["items"][0]["filename"] == "a.txt"
    d = api.get(f"{B}/documents").json()["items"][0]["id"]
    assert api.get(f"{B}/documents/{d}/download").content == b"kept"
    vault.reset_for_tests()


def test_production_mode_refuses_to_run_without_a_master_key(monkeypatch):
    vault.reset_for_tests()
    monkeypatch.delenv("REDEEM_MASTER_KEY", raising=False)
    monkeypatch.setenv("REDEEM_ENV", "production")
    with pytest.raises(vault.VaultError):
        vault.current_kek_id()
    vault.reset_for_tests()
