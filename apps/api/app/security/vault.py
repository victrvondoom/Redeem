"""Encryption at rest for user documents (AES-256-GCM).

- File bytes: per-tenant key = HKDF-SHA256(master, info="blob:<tenant_id>"); the tenant id is also bound as AAD, so a blob copied into another tenant's folder fails to decrypt.
- Extracted text in the DB: stored as ``enc1:<b64>`` via the EncryptedText column type, keyed from the master key (the column has no tenant context).
Limits (stated honestly): the master key lives on the server (env REDEEM_MASTER_KEY, else a 0600 file in the data dir). This protects database dumps and disk copies;
it is not end-to-end encryption and the server can decrypt while serving the owner's authenticated request.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from ..config import settings

MAGIC = b"RDM1"
_master: bytes | None = None


def _master_key() -> bytes:
    global _master
    if _master is not None:
        return _master
    env = os.environ.get("REDEEM_MASTER_KEY", "")
    if env:
        _master = base64.urlsafe_b64decode(env + "=" * (-len(env) % 4))
        if len(_master) < 32:
            raise RuntimeError("REDEEM_MASTER_KEY must decode to at least 32 bytes")
        return _master
    p = Path(settings.data_dir) / ".master_key"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    _master = p.read_bytes()
    return _master


def _key(info: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info.encode()).derive(_master_key())


def encrypt_bytes(tenant_id: str, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(_key(f"blob:{tenant_id}")).encrypt(nonce, data, tenant_id.encode())


def decrypt_bytes(tenant_id: str, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        return blob  # legacy plaintext blob written before encryption was enabled
    return AESGCM(_key(f"blob:{tenant_id}")).decrypt(blob[4:16], blob[16:], tenant_id.encode())


def write_blob(path: Path, tenant_id: str, data: bytes) -> None:
    path.write_bytes(encrypt_bytes(tenant_id, data))


def read_blob(path: str | Path, tenant_id: str) -> bytes:
    return decrypt_bytes(tenant_id, Path(path).read_bytes())


class EncryptedText(TypeDecorator):
    """Text column that is AES-GCM encrypted in the database and transparent in Python."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value.startswith("enc1:"):
            return value
        nonce = secrets.token_bytes(12)
        ct = AESGCM(_key("text")).encrypt(nonce, value.encode(), b"text")
        return "enc1:" + base64.urlsafe_b64encode(nonce + ct).decode()

    def process_result_value(self, value, dialect):
        if value is None or not value.startswith("enc1:"):
            return value
        raw = base64.urlsafe_b64decode(value[5:])
        return AESGCM(_key("text")).decrypt(raw[:12], raw[12:], b"text").decode()
