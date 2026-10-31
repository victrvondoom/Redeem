"""Envelope encryption at rest (AES-256-GCM) with key ids, versions and rotation.

Hierarchy
- KEK (key-encryption key): 32+ bytes from ``REDEEM_MASTER_KEY`` (base64url). ``REDEEM_MASTER_KEY_PREVIOUS`` (comma list) keeps older KEKs usable for
  decrypt/re-wrap after a rotation. Each KEK has an id ``kek_<sha256[:8]>``. In ``REDEEM_ENV=production`` a missing KEK is a hard error (fail closed);
  in development a 0600 key file is created in the data dir.
- Tenant DEKs (data-encryption keys): random 32 bytes per tenant and version, stored **wrapped** by a KEK in ``encryption_keys``. Used for document
  bytes and memory values. Rotating a tenant DEK creates a new active version; old versions stay for decrypt until ``reencrypt_*`` moves data.
- System DEK: derived (HKDF) from a KEK, used only for the database text column type that has no tenant context (``EncryptedText``).

Wire formats: blob ``RDM2`` + kid(24 ascii) + nonce(12) + ct; text ``enc2:<kid>:<b64(nonce+ct)>``. Legacy ``RDM1``/``enc1:`` data is still readable.
Honest limits: the application server can decrypt while serving an authenticated owner; this is not end-to-end encryption. A KMS is not integrated;
the KEK is supplied by environment/secret manager. Tenant id is bound as AAD so ciphertext moved between tenants fails authentication.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text, select
from sqlalchemy.types import TypeDecorator

from ..config import settings

MAGIC1, MAGIC2 = b"RDM1", b"RDM2"
KID_LEN = 24
_keks: dict[str, bytes] | None = None
_current: str | None = None
_dek_cache: dict[str, bytes] = {}


class VaultError(RuntimeError):
    pass


def _b64d(v: str) -> bytes:
    return base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))


def _kid(key: bytes) -> str:
    return "kek_" + hashlib.sha256(key).hexdigest()[:8]


def reset_for_tests() -> None:
    global _keks, _current
    _keks, _current = None, None
    _dek_cache.clear()


def _load() -> None:
    global _keks, _current
    if _keks is not None:
        return
    keys: dict[str, bytes] = {}
    cur = os.environ.get("REDEEM_MASTER_KEY", "")
    prod = os.environ.get("REDEEM_ENV", "").lower() == "production"
    if cur:
        k = _b64d(cur)
        if len(k) < 32:
            raise VaultError("REDEEM_MASTER_KEY must decode to at least 32 bytes")
        keys[_kid(k)] = k
        _current = _kid(k)
    elif prod:
        raise VaultError("REDEEM_MASTER_KEY is required when REDEEM_ENV=production (refusing to run without a key)")
    else:
        p = Path(settings.data_dir) / ".master_key"
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32))
        k = p.read_bytes()
        keys[_kid(k)] = k
        _current = _kid(k)
    for prev in filter(None, (x.strip() for x in os.environ.get("REDEEM_MASTER_KEY_PREVIOUS", "").split(","))):
        pk = _b64d(prev)
        keys[_kid(pk)] = pk
    _keks = keys


def current_kek_id() -> str:
    _load()
    assert _current
    return _current


def _kek(kid: str) -> bytes:
    _load()
    assert _keks is not None
    if kid not in _keks:
        raise VaultError(f"KEK {kid} is not available (set REDEEM_MASTER_KEY_PREVIOUS)")
    return _keks[kid]


def _system_dek(kek_id: str) -> tuple[str, bytes]:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"system-dek").derive(_kek(kek_id))
    return "sys_" + kek_id[4:], key


def _system_dek_by_kid(kid: str) -> bytes:
    _load()
    assert _keks is not None
    for kek_id in _keks:
        k, v = _system_dek(kek_id)
        if k == kid:
            return v
    raise VaultError(f"system key {kid} unavailable")


# ---------------------------------------------------------------- tenant DEKs (wrapped in the DB)
def _wrap(kek_id: str, dek: bytes, aad: str) -> str:
    n = secrets.token_bytes(12)
    return base64.urlsafe_b64encode(n + AESGCM(_kek(kek_id)).encrypt(n, dek, aad.encode())).decode()


def _unwrap(kek_id: str, wrapped: str, aad: str) -> bytes:
    raw = _b64d(wrapped)
    return AESGCM(_kek(kek_id)).decrypt(raw[:12], raw[12:], aad.encode())


def _models():
    from ..models import EncryptionKey
    return EncryptionKey


def _active(db, tenant_id: str):
    EK = _models()
    row = db.scalar(select(EK).where(EK.scope == tenant_id, EK.status == "active").order_by(EK.version.desc()))
    if row:
        return row
    row = EK(scope=tenant_id, version=1, kek_id=current_kek_id(), status="active", wrapped=_wrap(current_kek_id(), secrets.token_bytes(32), "pending"))
    db.add(row)
    db.flush()
    dek = secrets.token_bytes(32)
    row.wrapped = _wrap(row.kek_id, dek, row.id)
    db.flush()
    _dek_cache[row.id] = dek
    return row


def _dek(db, key_id: str) -> bytes:
    if key_id in _dek_cache:
        return _dek_cache[key_id]
    row = db.get(_models(), key_id)
    if not row:
        raise VaultError("data key not found")
    d = _unwrap(row.kek_id, row.wrapped, row.id)
    _dek_cache[key_id] = d
    return d


def _pad(kid: str) -> bytes:
    assert len(kid) <= KID_LEN
    return kid.ljust(KID_LEN).encode()


def encrypt_bytes(db, tenant_id: str, data: bytes) -> bytes:
    row = _active(db, tenant_id)
    n = secrets.token_bytes(12)
    return MAGIC2 + _pad(row.id) + n + AESGCM(_dek(db, row.id)).encrypt(n, data, tenant_id.encode())


def decrypt_bytes(db, tenant_id: str, blob: bytes) -> bytes:
    if blob.startswith(MAGIC2):
        kid = blob[4:4 + KID_LEN].decode().strip()
        o = 4 + KID_LEN
        return AESGCM(_dek(db, kid)).decrypt(blob[o:o + 12], blob[o + 12:], tenant_id.encode())
    if blob.startswith(MAGIC1):  # v1: per-tenant HKDF of the first KEK
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"blob:{tenant_id}".encode()).derive(_kek(current_kek_id()))
        return AESGCM(key).decrypt(blob[4:16], blob[16:], tenant_id.encode())
    return blob  # legacy plaintext


def encrypt_str(db, tenant_id: str, text: str) -> str:
    row = _active(db, tenant_id)
    n = secrets.token_bytes(12)
    ct = AESGCM(_dek(db, row.id)).encrypt(n, text.encode(), tenant_id.encode())
    return f"enc2t:{row.id}:{base64.urlsafe_b64encode(n + ct).decode()}"


def decrypt_str(db, tenant_id: str, value: str) -> str:
    if not value.startswith("enc2t:"):
        return value
    _, kid, b = value.split(":", 2)
    raw = _b64d(b)
    return AESGCM(_dek(db, kid)).decrypt(raw[:12], raw[12:], tenant_id.encode()).decode()


def write_blob(db, path: Path, tenant_id: str, data: bytes) -> None:
    path.write_bytes(encrypt_bytes(db, tenant_id, data))


def read_blob(db, path: str | Path, tenant_id: str) -> bytes:
    return decrypt_bytes(db, tenant_id, Path(path).read_bytes())


# ---------------------------------------------------------------- rotation / status
def rotate_tenant_dek(db, tenant_id: str):
    """New active DEK version for a tenant. Old versions stay (decrypt-only) until data is re-encrypted."""
    EK = _models()
    cur = _active(db, tenant_id)
    cur.status = "retired"
    db.flush()
    row = EK(scope=tenant_id, version=cur.version + 1, kek_id=current_kek_id(), status="active", wrapped="x")
    db.add(row)
    db.flush()
    dek = secrets.token_bytes(32)
    row.wrapped = _wrap(row.kek_id, dek, row.id)
    _dek_cache[row.id] = dek
    db.flush()
    return row


def rewrap_all(db) -> int:
    """After a KEK rotation (new REDEEM_MASTER_KEY + old one in REDEEM_MASTER_KEY_PREVIOUS): re-wrap every DEK under the current KEK."""
    EK = _models()
    n = 0
    for row in db.scalars(select(EK)):
        if row.kek_id != current_kek_id():
            dek = _unwrap(row.kek_id, row.wrapped, row.id)
            row.wrapped, row.kek_id = _wrap(current_kek_id(), dek, row.id), current_kek_id()
            n += 1
    db.flush()
    return n


def status(db, tenant_id: str) -> dict:
    EK = _models()
    rows = list(db.scalars(select(EK).where(EK.scope == tenant_id).order_by(EK.version)))
    _load()
    prod = os.environ.get("REDEEM_ENV", "").lower() == "production"
    return {"algorithm": "AES-256-GCM", "scheme": "envelope: per-workspace data keys wrapped by a key-encryption key",
            "kek_id": current_kek_id(), "kek_source": "environment (REDEEM_MASTER_KEY)" if os.environ.get("REDEEM_MASTER_KEY") else "development key file (not for production)",
            "production_mode": prod, "kms_integrated": False,
            "key_versions": [{"id": r.id, "version": r.version, "status": r.status, "kek_id": r.kek_id, "created_at": r.created_at.isoformat()} for r in rows],
            "encrypted": ["uploaded document bytes", "extracted document text", "saved memory values", "connector credentials (see connectors)"],
            "not_encrypted_at_application_layer": ["mission/case titles and metadata", "ledger events", "account email and name", "database files themselves (use disk/volume encryption)"],
            "end_to_end": False}


class EncryptedText(TypeDecorator):
    """Text column encrypted with the system DEK (no tenant context available at the column level)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value.startswith(("enc1:", "enc2:")):
            return value
        kid, key = _system_dek(current_kek_id())
        n = secrets.token_bytes(12)
        return f"enc2:{kid}:" + base64.urlsafe_b64encode(n + AESGCM(key).encrypt(n, value.encode(), b"text")).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if value.startswith("enc2:"):
            _, kid, b = value.split(":", 2)
            raw = _b64d(b)
            return AESGCM(_system_dek_by_kid(kid)).decrypt(raw[:12], raw[12:], b"text").decode()
        if value.startswith("enc1:"):
            raw = _b64d(value[5:])
            key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"text").derive(_kek(current_kek_id()))
            return AESGCM(key).decrypt(raw[:12], raw[12:], b"text").decode()
        return value
