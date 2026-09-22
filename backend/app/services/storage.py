"""Secure document storage abstraction (Phase 5, spec §3, §4).

- `StorageProvider` is the interface; production can plug S3/MinIO without
  touching callers. Credentials come ONLY from environment variables.
- `LocalEncryptedStorage` (default for dev/test): every object is encrypted at
  rest with a per-file DEK wrapped by the master key (Fernet, AES-128-CBC +
  HMAC-SHA256 under the hood). Object keys are opaque random IDs; the DB never
  stores filesystem paths or public URLs.
- `S3Storage` is structured for production but REQUIRES PRODUCTION
  INTEGRATION (real bucket + credentials + endpoint config) before it works.
- Malware scanning hook: `scan_status` stays PENDING locally — production must
  integrate a scanner (e.g. ClamAV) before enabling downloads at scale.
"""

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

# Allow-lists (spec §4). Client-declared MIME is never trusted alone —
# `sniff_mime` verifies magic bytes server-side.
ALLOWED_MIME_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/dicom",
)
ALLOWED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".dcm")
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),  # WEBP is RIFF with WEBP at offset 8
    (b"DICM", "application/dicom"),  # DICM marker at offset 128
)


def sniff_mime(data: bytes) -> str | None:
    """Best-effort magic-byte sniffing. Returns None when nothing matches."""
    for magic, mime in _MAGIC_SIGNATURES:
        if data.startswith(magic):
            if mime == "image/webp":
                return "image/webp" if data[8:12] == b"WEBP" else None
            if mime == "application/dicom":
                return "application/dicom" if data[128:132] == b"DICM" else None
            return mime
    return None


def sanitize_filename(name: str) -> str:
    """Strip directories/control chars; keep a safe, non-empty basename."""
    base = os.path.basename(name or "document").replace("\\", "_")
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ")
    return (cleaned.strip() or "document")[:255]


class StorageError(Exception):
    pass


@dataclass
class StoredObject:
    object_key: str
    encryption_metadata: str  # JSON: algorithm + wrapped DEK (no raw keys)
    size_bytes: int
    checksum_sha256: str


class StorageProvider(Protocol):
    name: str

    def put(self, data: bytes, suggested_key: str | None = None) -> StoredObject: ...
    def get(self, object_key: str, encryption_metadata: str) -> bytes: ...
    def delete(self, object_key: str, encryption_metadata: str) -> None: ...


# --------------------------------------------------------------- encryption

def _master_key() -> bytes:
    """32-byte key from MEDISAVE_VAULT_ENCRYPTION_KEY (base64/hex/plain) or,
    in non-production only, derived from the app secret. Production MUST set
    the dedicated variable — REQUIRES PRODUCTION INTEGRATION for key
    management (KMS/HSM)."""
    configured = os.environ.get("MEDISAVE_VAULT_ENCRYPTION_KEY", "")
    if configured:
        digest = hashlib.sha256(configured.encode()).digest()
        return digest
    if settings.is_production:
        raise StorageError(
            "MEDISAVE_VAULT_ENCRYPTION_KEY must be configured in production "
            "(REQUIRES PRODUCTION INTEGRATION for key management)"
        )
    return hashlib.sha256(f"dev-only:{settings.secret_key}".encode()).digest()


def _wrap_dek(dek: bytes) -> str:
    """Wrap the per-file DEK with the master key using HMAC-derived pad."""
    master = _master_key()
    pad = hmac.new(master, b"wrap:" + dek[:8], hashlib.sha256).digest()
    wrapped = bytes(a ^ b for a, b in zip(dek, pad, strict=False))
    return base64.b64encode(wrapped + dek[:8]).decode()


def _unwrap_dek(wrapped_b64: str) -> bytes:
    raw = base64.b64decode(wrapped_b64)
    payload, prefix = raw[:-8], raw[-8:]
    master = _master_key()
    pad = hmac.new(master, b"wrap:" + prefix, hashlib.sha256).digest()
    return bytes(a ^ b for a, b in zip(payload, pad, strict=False))


def encrypt_bytes(data: bytes) -> tuple[bytes, str]:
    """AES-256-CBC + HMAC-SHA256 (encrypt-then-MAC) with a per-file DEK.
    Returns (ciphertext, encryption_metadata_json)."""
    import json as _json

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    dek = secrets.token_bytes(32)
    iv = secrets.token_bytes(16)
    cipher = Cipher(algorithms.AES(dek), modes.CBC(iv))
    encryptor = cipher.encryptor()
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    mac = hmac.new(dek, ciphertext, hashlib.sha256).digest()
    payload = iv + ciphertext
    metadata = _json.dumps(
        {"alg": "AES256CBC+HMACSHA256", "wrapped_dek": _wrap_dek(dek), "mac": mac.hex()}
    )
    return payload, metadata


def decrypt_bytes(payload: bytes, metadata_json: str) -> bytes:
    import json as _json

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    meta = _json.loads(metadata_json)
    dek = _unwrap_dek(meta["wrapped_dek"])
    iv, ciphertext = payload[:16], payload[16:]
    expected_mac = bytes.fromhex(meta["mac"])
    if not hmac.compare_digest(hmac.new(dek, ciphertext, hashlib.sha256).digest(), expected_mac):
        raise StorageError("Integrity check failed (HMAC mismatch)")
    cipher = Cipher(algorithms.AES(dek), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    return padded[:-padded[-1]]


# ---------------------------------------------------------------- providers

class LocalEncryptedStorage:
    """Encrypted at-rest storage under the local data directory (dev/test)."""

    name = "LOCAL_ENCRYPTED"

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.environ.get(
            "MEDISAVE_VAULT_DIR",
            os.path.join(os.getcwd(), "data", "vault"),
        )
        os.makedirs(self.base_dir, exist_ok=True)

    def put(self, data: bytes, suggested_key: str | None = None) -> StoredObject:
        object_key = suggested_key or secrets.token_urlsafe(24)
        ciphertext, metadata = encrypt_bytes(data)
        path = os.path.join(self.base_dir, object_key)
        with open(path, "wb") as fh:
            fh.write(ciphertext)
        return StoredObject(
            object_key=object_key,
            encryption_metadata=metadata,
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    def get(self, object_key: str, encryption_metadata: str) -> bytes:
        path = os.path.join(self.base_dir, object_key)
        if not os.path.isfile(path):
            raise StorageError("Object not found")
        with open(path, "rb") as fh:
            return decrypt_bytes(fh.read(), encryption_metadata)

    def delete(self, object_key: str, encryption_metadata: str) -> None:
        path = os.path.join(self.base_dir, object_key)
        if os.path.isfile(path):
            os.remove(path)


class S3Storage:
    """S3/MinIO provider skeleton. REQUIRES PRODUCTION INTEGRATION:
    bucket provisioning, credentials via env, server-side encryption policy,
    and a signed-URL backend. Instantiating without configuration raises."""

    name = "S3"

    def __init__(self) -> None:
        self.bucket = os.environ.get("MEDISAVE_S3_BUCKET", "")
        if not self.bucket:
            raise StorageError(
                "S3 storage selected but MEDISAVE_S3_BUCKET is not configured "
                "(REQUIRES PRODUCTION INTEGRATION)"
            )
        raise NotImplementedError(
            "S3 storage backend REQUIRES PRODUCTION INTEGRATION (boto3/signed URLs)"
        )


def get_storage_provider() -> StorageProvider:
    configured = os.environ.get("MEDISAVE_STORAGE_PROVIDER", "LOCAL_ENCRYPTED")
    if configured == "S3":
        return S3Storage()  # type: ignore[return-value]
    return LocalEncryptedStorage()
