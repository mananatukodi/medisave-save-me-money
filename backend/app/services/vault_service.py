"""Digital Health Vault service (Phase 5, spec §5-§9, §15).

Authorization model (checked on EVERY access — never inferred from roles):
- owner (patient) → full control of own records
- active share (scope + expiry + not revoked) → scoped access only
- everyone else, including SUPPORT_AGENT / HOSPITAL_ADMIN / SUPER_ADMIN → 404/403

Every sensitive access — successful or denied — writes BOTH an audit-log row
and a per-record access event. Document contents are never logged.
"""

import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.consent import Consent
from app.models.ops import AuditLog
from app.models.vault import (
    SHARE_SCOPES,
    HealthRecord,
    HealthRecordAccessEvent,
    HealthRecordShare,
    StoredFile,
)
from app.services.storage import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    StorageError,
    get_storage_provider,
    sanitize_filename,
    sniff_mime,
)


class VaultError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


DOWNLOAD_URL_TTL_SECONDS = 900  # 15 minutes maximum (spec §15 short expiry)


def _event(
    db: Session,
    *,
    record_id: str,
    patient_id: str,
    actor_user_id: str | None,
    action: str,
    result: str = "SUCCESS",
    reason: str = "",
) -> None:
    db.add(
        HealthRecordAccessEvent(
            record_id=record_id,
            patient_id=patient_id,
            actor_user_id=actor_user_id,
            action=action,
            result=result,
            reason=reason[:200],
        )
    )


def _audit(
    db: Session,
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    action: str,
    resource_id: str | None,
    outcome: str = "SUCCESS",
    detail: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            resource_type="health_record",
            resource_id=resource_id,
            outcome=outcome,
            detail=detail[:500],
        )
    )


# ----------------------------------------------------------------- upload

def validate_upload(filename: str, declared_mime: str, data: bytes) -> tuple[str, str]:
    """Server-side validation (spec §4). Returns (safe_filename, sniffed_mime).
    Raises VaultError(422) on any violation."""
    if len(data) == 0:
        raise VaultError("Empty file", 422)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise VaultError(
            f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit", 422
        )
    safe_name = sanitize_filename(filename)
    ext = "." in safe_name and ("." + safe_name.rsplit(".", 1)[1].lower()) or ""
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise VaultError(f"Extension {ext} not allowed", 422)
    sniffed = sniff_mime(data)
    if sniffed is None:
        raise VaultError("Unrecognized file type (magic-byte validation failed)", 422)
    if declared_mime and declared_mime not in ALLOWED_MIME_TYPES:
        raise VaultError(f"MIME type {declared_mime} not allowed", 422)
    if sniffed not in ALLOWED_MIME_TYPES:
        raise VaultError(f"Detected content type {sniffed} not allowed", 422)
    if declared_mime and sniffed != declared_mime:
        # Client-declared type must agree with the actual bytes (spec §4).
        raise VaultError("Declared MIME type does not match the file content", 422)
    return safe_name, sniffed


def attach_file(
    db: Session,
    record: HealthRecord,
    *,
    filename: str,
    declared_mime: str,
    data: bytes,
    actor_user_id: str,
) -> StoredFile:
    safe_name, sniffed = validate_upload(filename, declared_mime, data)
    provider = get_storage_provider()
    stored = provider.put(data)
    stale = record.file_id
    stored_file = StoredFile(
        owner_id=record.patient_id,
        object_key=stored.object_key,
        original_filename=safe_name,
        mime_type=sniffed,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
        storage_provider=provider.name,
        encryption_metadata=stored.encryption_metadata,
        upload_status="COMPLETED",
        scan_status="PENDING",  # malware scanning REQUIRES PRODUCTION INTEGRATION
    )
    db.add(stored_file)
    db.flush()
    record.file_id = stored_file.id
    _event(
        db,
        record_id=record.id,
        patient_id=record.patient_id,
        actor_user_id=actor_user_id,
        action="FILE_UPLOADED",
    )
    _audit(
        db,
        actor_user_id=actor_user_id,
        actor_role="PATIENT",
        action="FILE_UPLOADED",
        resource_id=record.id,
        detail=(
            f"file={safe_name} mime={sniffed} bytes={stored.size_bytes} "
            f"sha256={stored.checksum_sha256[:12]}"
        ),
    )
    # Best-effort cleanup of a replaced file (never deletes other records' files)
    if stale:
        old = db.get(StoredFile, stale)
        if old is not None and old.object_key != stored_file.object_key:
            try:
                provider.delete(old.object_key, old.encryption_metadata)
            except StorageError:
                pass
            db.delete(old)
    db.flush()
    return stored_file


# ---------------------------------------------------------- authorization

def _load_record(db: Session, record_id: str) -> HealthRecord:
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise VaultError("Record not found", 404)
    return record


def _authorize_family(
    db: Session,
    *,
    record: HealthRecord,
    user,
    required_scope: str,
) -> tuple[str, str]:
    """Family-consent branch (Phase 6). A relationship grants nothing by
    itself; access requires an ACTIVE relationship owned by the record's
    patient PLUS an ACTIVE FamilyAccessConsent with VIEW_HEALTH_RECORDS and a
    matching category filter. Family consent authorizes VIEW only — downloads
    stay owner/direct-share. Returns:
    ("allow", "")        — authorized via family consent
    ("deny", reason)     — related but unauthorized (→ 403, audited)
    ("none", "")         — no family relationship (→ fall through to 404)
    """
    from app.models.family import FamilyRelationship
    from app.services import family_service

    rel = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == record.patient_id,
            FamilyRelationship.member_user_id == user.id,
        )
        .first()
    )
    if rel is None:
        return "none", ""
    if rel.status != "ACTIVE":
        # A relationship row exists (invited/declined/revoked/expired): deny
        # explicitly (403) rather than existence-hide, mirroring the revoked-
        # share convention.
        return "deny", "relationship_not_active"
    consent = family_service.active_consent(db, rel.id)
    if consent is None:
        return "deny", "no_active_family_consent"
    if required_scope != "VIEW_RECORD" or "VIEW_HEALTH_RECORDS" not in consent.scope_list:
        return "deny", "insufficient_family_scope"
    if consent.categories and record.category not in consent.categories:
        return "deny", "category_out_of_scope"
    _audit(
        db,
        actor_user_id=user.id,
        actor_role=",".join(user.role_ids) or None,
        action="FAMILY_RECORD_ACCESS",
        resource_id=record.id,
        detail=f"relationship={rel.id} scopes={consent.scopes}",
    )
    db.commit()
    return "allow", ""


def authorize_access(
    db: Session,
    record: HealthRecord,
    user,
    *,
    required_scope: str,
) -> HealthRecordShare | None:
    """Return the active share granting access, or None when the user is the
    owner. Raises VaultError (403/404) otherwise — with an audited DENIED event."""
    if record.patient_id == user.id:
        return None
    if required_scope not in SHARE_SCOPES:
        raise VaultError("Invalid scope", 422)

    share = (
        db.query(HealthRecordShare)
        .filter(
            HealthRecordShare.record_id == record.id,
            HealthRecordShare.grantee_user_id == user.id,
        )
        .order_by(HealthRecordShare.granted_at.desc())
        .first()
    )
    if share is None:
        # Phase 6: family-consent branch. A relationship alone grants nothing;
        # an ACTIVE relationship + ACTIVE consent with VIEW_HEALTH_RECORDS
        # (+ matching category filter) authorizes VIEW_RECORD only. Everything
        # else falls through to the audited denial below.
        outcome, family_reason = _authorize_family(
            db, record=record, user=user, required_scope=required_scope
        )
        if outcome == "allow":
            return None  # authorized via family consent; no share object
        if outcome == "deny":
            _event(
                db,
                record_id=record.id,
                patient_id=record.patient_id,
                actor_user_id=user.id,
                action="DENIED",
                result="DENIED",
                reason=family_reason,
            )
            _audit(
                db,
                actor_user_id=user.id,
                actor_role=",".join(user.role_ids) or None,
                action="FAMILY_RECORD_ACCESS_DENIED",
                resource_id=record.id,
                outcome="DENIED",
                detail=f"scope={required_scope} reason={family_reason}",
            )
            db.commit()
            raise VaultError("You do not have access to this record", 403)
        # outcome == "none": no family relationship — fall through to 404.
    denied = False
    reason = ""
    if share is None:
        denied, reason = True, "no_active_share"
    elif not share.is_active:
        # A share row exists but is revoked/expired: explicit denial (403),
        # distinct from the existence-hiding 404 for total strangers.
        denied, reason = True, "share_expired_or_revoked"
    elif required_scope == "DOWNLOAD_RECORD" and share.scope == "VIEW_RECORD":
        denied, reason = True, "insufficient_scope"

    if denied:
        _event(
            db,
            record_id=record.id,
            patient_id=record.patient_id,
            actor_user_id=user.id,
            action="DENIED",
            result="DENIED",
            reason=reason,
        )
        _audit(
            db,
            actor_user_id=user.id,
            actor_role=",".join(user.role_ids) or None,
            action="RECORD_ACCESS_DENIED",
            resource_id=record.id,
            outcome="DENIED",
            detail=f"scope={required_scope} reason={reason}",
        )
        db.commit()
        # 404 when the caller has no relationship at all: do not leak the
        # existence of other patients' records (no IDOR, spec §18-H).
        if share is None:
            raise VaultError("Record not found", 404)
        raise VaultError("You do not have access to this record", 403)

    if share.scope == "VIEW_CATEGORY" and share.category_filter:
        allowed_categories = [c.strip() for c in share.category_filter.split(",") if c.strip()]
        if record.category not in allowed_categories:
            _event(
                db,
                record_id=record.id,
                patient_id=record.patient_id,
                actor_user_id=user.id,
                action="DENIED",
                result="DENIED",
                reason="category_out_of_scope",
            )
            db.commit()
            raise VaultError("This share does not cover this record category", 403)
    return share


def get_record_for_user(db: Session, record_id: str, user) -> tuple[HealthRecord, HealthRecordShare | None]:
    record = _load_record(db, record_id)
    share = authorize_access(db, record, user, required_scope="VIEW_RECORD")
    _event(
        db,
        record_id=record.id,
        patient_id=record.patient_id,
        actor_user_id=user.id,
        action="VIEW",
    )
    db.commit()
    return record, share


# ------------------------------------------------------------------ shares

def create_share(
    db: Session,
    record: HealthRecord,
    *,
    grantee_user_id: str,
    grantee_type: str,
    scope: str,
    category_filter: str,
    purpose: str,
    expires_at: datetime | None,
    actor,
) -> HealthRecordShare:
    if record.patient_id != actor.id:
        raise VaultError("Only the patient can share this record", 403)
    if scope not in SHARE_SCOPES:
        raise VaultError(f"scope must be one of {SHARE_SCOPES}", 422)
    if grantee_user_id == actor.id:
        raise VaultError("Cannot share with yourself", 422)

    # One auditable consent ledger: every share is mirrored as a DOCUMENT_SHARE consent.
    consent = Consent(
        user_id=actor.id,
        consent_type="DOCUMENT_SHARE",
        purpose=purpose or "Health record share",
        data_scope=scope,
        recipient=grantee_type,
        expires_at=expires_at,
    )
    db.add(consent)
    db.flush()

    share = HealthRecordShare(
        record_id=record.id,
        consent_id=consent.id,
        granted_by=actor.id,
        grantee_user_id=grantee_user_id,
        grantee_type=grantee_type,
        scope=scope,
        category_filter=category_filter,
        purpose=purpose,
        expires_at=expires_at,
    )
    db.add(share)
    db.flush()
    _event(
        db,
        record_id=record.id,
        patient_id=record.patient_id,
        actor_user_id=actor.id,
        action="SHARE_CREATED",
    )
    _audit(
        db,
        actor_user_id=actor.id,
        actor_role="PATIENT",
        action="RECORD_SHARED",
        resource_id=record.id,
        detail=f"share={share.id} scope={scope} grantee_type={grantee_type}",
    )
    db.flush()
    return share


def revoke_share(db: Session, share: HealthRecordShare, actor) -> HealthRecordShare:
    if share.granted_by != actor.id:
        raise VaultError("Only the granting patient can revoke this share", 403)
    if share.revoked_at is not None:
        raise VaultError("Share already revoked", 409)
    share.revoked_at = datetime.now(UTC)
    if share.consent_id:
        consent = db.get(Consent, share.consent_id)
        if consent is not None and consent.revoked_at is None:
            consent.revoked_at = datetime.now(UTC)
    _event(
        db,
        record_id=share.record_id,
        patient_id=share.granted_by,
        actor_user_id=actor.id,
        action="SHARE_REVOKED",
    )
    _audit(
        db,
        actor_user_id=actor.id,
        actor_role="PATIENT",
        action="SHARE_REVOKED",
        resource_id=share.record_id,
        detail=f"share={share.id}",
    )
    db.flush()
    return share


def list_shared_records(db: Session, user) -> list[tuple[HealthRecord, HealthRecordShare]]:
    """Records currently shared with this user (active shares only)."""
    shares = (
        db.query(HealthRecordShare)
        .filter(
            HealthRecordShare.grantee_user_id == user.id,
            HealthRecordShare.revoked_at.is_(None),
        )
        .order_by(HealthRecordShare.granted_at.desc())
        .all()
    )
    active: list[tuple[HealthRecord, HealthRecordShare]] = []
    for share in shares:
        if not share.is_active:
            continue
        record = db.get(HealthRecord, share.record_id)
        if record is None or record.deleted_at is not None:
            continue
        if share.scope == "VIEW_CATEGORY" and share.category_filter:
            allowed = [c.strip() for c in share.category_filter.split(",") if c.strip()]
            if record.category not in allowed:
                continue
        active.append((record, share))
    return active


# ------------------------------------------------------------- signed URLs

def _sign(payload: str) -> str:
    mac = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode()


def generate_download_url(
    db: Session,
    record: HealthRecord,
    user,
) -> dict:
    """Short-lived signed download token (spec §15). Authorization is checked
    fresh on every call — a revoked share immediately blocks new URLs."""
    authorize_access(db, record, user, required_scope="DOWNLOAD_RECORD")
    if record.file_id is None:
        raise VaultError("Record has no attached document", 404)
    stored_file = db.get(StoredFile, record.file_id)
    if stored_file is None or stored_file.upload_status != "COMPLETED":
        raise VaultError("Document is not available for download", 409)

    expires = int(time.time()) + DOWNLOAD_URL_TTL_SECONDS
    payload = f"{stored_file.id}.{expires}"
    token = f"{payload}.{_sign(payload)}"
    _event(
        db,
        record_id=record.id,
        patient_id=record.patient_id,
        actor_user_id=user.id,
        action="DOWNLOAD_URL",
    )
    _audit(
        db,
        actor_user_id=user.id,
        actor_role=",".join(user.role_ids) or None,
        action="SIGNED_URL_GENERATED",
        resource_id=record.id,
        detail=f"ttl={DOWNLOAD_URL_TTL_SECONDS}s file={stored_file.original_filename}",
    )
    db.commit()
    return {
        "url": f"/api/v1/health-records/files/{token}",
        "expires_at": datetime.fromtimestamp(expires, tz=UTC).isoformat(),
        "ttl_seconds": DOWNLOAD_URL_TTL_SECONDS,
        "filename": stored_file.original_filename,
        "mime_type": stored_file.mime_type,
        "scan_status": stored_file.scan_status,  # PENDING locally — honest label
    }


def resolve_download_token(db: Session, token: str) -> tuple[StoredFile, HealthRecord]:
    """Validate signature + expiry. Returns the file + owning record; the
    caller streams bytes. No authorization bypass: the token only proves the
    URL was generated through `generate_download_url` within its TTL."""
    try:
        file_id, expires_str, signature = token.split(".", 2)
        expires = int(expires_str)
    except ValueError:
        raise VaultError("Malformed download token", 400) from None
    payload = f"{file_id}.{expires_str}"
    if not hmac.compare_digest(_sign(payload), signature):
        raise VaultError("Invalid download token signature", 403)
    if time.time() > expires:
        raise VaultError("Download URL expired", 403)
    stored_file = db.get(StoredFile, file_id)
    if stored_file is None:
        raise VaultError("Object not found", 404)
    record = (
        db.query(HealthRecord).filter(HealthRecord.file_id == stored_file.id).first()
    )
    if record is None or record.deleted_at is not None:
        raise VaultError("Record not found", 404)
    return stored_file, record
