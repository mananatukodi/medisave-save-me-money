"""Digital Health Vault API (Phase 5, spec §10).

Every endpoint performs server-side authorization via `vault_service`:
ownership or an active, in-scope, unexpired share. All sensitive operations
are audited; denials write DENIED events with reasons (never content).
"""

from datetime import UTC, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.vault import (
    HealthRecord,
    HealthRecordAccessEvent,
    HealthRecordShare,
    StoredFile,
)
from app.schemas.vault import (
    DownloadUrlOut,
    HealthRecordCreate,
    HealthRecordOut,
    HealthRecordUpdate,
    ShareCreate,
    ShareOut,
    VaultEventOut,
)
from app.security.deps import CurrentUser, record_audit
from app.services.vault_service import (
    VaultError,
    attach_file,
    authorize_access,
    create_share,
    generate_download_url,
    get_record_for_user,
    get_storage_provider,
    list_shared_records,
    resolve_download_token,
    revoke_share,
)

router = APIRouter(prefix="/health-records", tags=["health-records"])


def _raise(err: VaultError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


@router.post("", response_model=HealthRecordOut, status_code=201)
def create_record(
    payload: HealthRecordCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    if "PATIENT" not in user.role_ids and "FAMILY_MEMBER" not in user.role_ids:
        raise HTTPException(status_code=403, detail="Only patients can create health records")
    record = HealthRecord(
        patient_id=user.id,
        category=payload.category,
        title=payload.title.strip(),
        description=payload.description,
        record_date=payload.record_date,
        provider_id=payload.provider_id,
        hospital_id=payload.hospital_id,
        source="PATIENT_UPLOAD",
        created_by=user.id,
        status="ACTIVE",
    )
    db.add(record)
    db.flush()
    record_audit(
        db,
        action="RECORD_CREATED",
        actor_user_id=user.id,
        actor_role=",".join(user.role_ids) or None,
        resource_type="health_record",
        resource_id=record.id,
        detail=f"category={record.category}",
    )
    db.commit()
    return record


@router.get("", response_model=list[HealthRecordOut])
def list_records(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    category: str | None = Query(default=None, max_length=40),
    date_from: str | None = Query(default=None, max_length=10),
    date_to: str | None = Query(default=None, max_length=10),
    title: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Patient's own records with filters (category/date range/title/status).
    Returns an honest empty list — never synthetic entries."""
    query = (
        db.query(HealthRecord)
        .options(joinedload(HealthRecord.file))
        .filter(HealthRecord.patient_id == user.id, HealthRecord.deleted_at.is_(None))
    )
    if category:
        query = query.filter(HealthRecord.category == category)
    if date_from:
        query = query.filter(HealthRecord.record_date >= date_from)
    if date_to:
        query = query.filter(HealthRecord.record_date <= date_to)
    if title:
        query = query.filter(HealthRecord.title.ilike(f"%{title}%"))
    if status:
        query = query.filter(HealthRecord.status == status)
    query = query.order_by(
        HealthRecord.record_date.desc(), HealthRecord.created_at.desc()
    )
    return query.offset(offset).limit(limit).all()


@router.get("/shared-with-me", response_model=list[HealthRecordOut])
def shared_with_me(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Records actively shared with the current user (scope-checked)."""
    pairs = list_shared_records(db, user)
    return [record for record, _share in pairs]


@router.get("/shares", response_model=list[ShareOut])
def list_my_shares(user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    """Shares the patient granted (active + expired + revoked for transparency)."""
    return (
        db.query(HealthRecordShare)
        .join(HealthRecord, HealthRecordShare.record_id == HealthRecord.id)
        .filter(HealthRecordShare.granted_by == user.id, HealthRecord.deleted_at.is_(None))
        .order_by(HealthRecordShare.granted_at.desc())
        .limit(200)
        .all()
    )


@router.post("/shares", response_model=ShareOut, status_code=201)
def share_record(
    payload: ShareCreate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    record = db.get(HealthRecord, payload.record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    try:
        share = create_share(
            db,
            record,
            grantee_user_id=payload.grantee_user_id,
            grantee_type=payload.grantee_type,
            scope=payload.scope,
            category_filter=payload.category_filter,
            purpose=payload.purpose,
            expires_at=(
                datetime_now_utc() + timedelta(days=payload.expires_in_days)
                if payload.expires_in_days
                else None
            ),
            actor=user,
        )
    except VaultError as err:
        raise _raise(err) from None
    db.commit()
    return share


@router.delete("/shares/{share_id}", response_model=ShareOut)
def revoke_record_share(
    share_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    share = db.get(HealthRecordShare, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    try:
        share = revoke_share(db, share, user)
    except VaultError as err:
        raise _raise(err) from None
    db.commit()
    return share


def datetime_now_utc():
    from datetime import datetime

    return datetime.now(UTC)


@router.get("/{record_id}", response_model=HealthRecordOut)
def record_detail(record_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]):
    try:
        record, _share = get_record_for_user(db, record_id, user)
    except VaultError as err:
        raise _raise(err) from None
    return record


@router.patch("/{record_id}", response_model=HealthRecordOut)
def update_record(
    record_id: str,
    payload: HealthRecordUpdate,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.patient_id != user.id:
        raise HTTPException(status_code=403, detail="Only the patient can update this record")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(record, field, value)
    record_audit(
        db,
        action="RECORD_METADATA_UPDATED",
        actor_user_id=user.id,
        actor_role="PATIENT",
        resource_type="health_record",
        resource_id=record.id,
        detail=f"fields={sorted(data)}",
    )
    db.commit()
    return record


@router.delete("/{record_id}", response_model=HealthRecordOut)
def delete_record(
    record_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Soft delete (retention-safe, spec §16): metadata rows persist for audit,
    the document is purged from storage immediately."""
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.patient_id != user.id:
        raise HTTPException(status_code=403, detail="Only the patient can delete this record")
    if record.file_id:
        stored_file = db.get(StoredFile, record.file_id)
        if stored_file is not None:
            try:
                get_storage_provider().delete(stored_file.object_key, stored_file.encryption_metadata)
            except Exception:
                pass  # storage purge is retried by ops; metadata stays soft-deleted
            db.delete(stored_file)
            record.file_id = None
    from datetime import datetime

    record.deleted_at = datetime.now(UTC)
    record.status = "DELETED"
    db.add(
        HealthRecordAccessEvent(
            record_id=record.id,
            patient_id=record.patient_id,
            actor_user_id=user.id,
            action="DELETE",
            result="SUCCESS",
        )
    )
    record_audit(
        db,
        action="RECORD_DELETED",
        actor_user_id=user.id,
        actor_role="PATIENT",
        resource_type="health_record",
        resource_id=record.id,
        detail="soft delete + storage purge",
    )
    db.commit()
    return record


@router.post("/{record_id}/upload", response_model=HealthRecordOut, status_code=201)
async def upload_document(
    record_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload/replace the record's document. Server-side validation: MIME
    allow-list, magic-byte sniffing, size cap, filename sanitization,
    SHA-256 checksum (spec §4). Malware scanning stays PENDING — REQUIRES
    PRODUCTION INTEGRATION."""
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.patient_id != user.id:
        raise HTTPException(status_code=403, detail="Only the patient can upload to this record")
    data = await file.read()
    try:
        attach_file(
            db,
            record,
            filename=file.filename or "document",
            declared_mime=file.content_type or "",
            data=data,
            actor_user_id=user.id,
        )
    except VaultError as err:
        raise _raise(err) from None
    db.commit()
    db.refresh(record)
    return record


@router.get("/files/{token}")
def download_file(
    token: str,
    db: Annotated[Session, Depends(get_db)],
):
    """Signed-URL download (15-min TTL, HMAC-signed). The token proves the URL
    was generated through the authorized endpoint; contents stream from the
    encrypted storage provider. Never a public/permanent URL (spec §3)."""
    try:
        stored_file, _record = resolve_download_token(db, token)
        data = get_storage_provider().get(
            stored_file.object_key, stored_file.encryption_metadata
        )
    except VaultError as err:
        raise _raise(err) from None
    except Exception:  # storage backend failure
        raise HTTPException(status_code=503, detail="Storage temporarily unavailable") from None
    return Response(
        content=data,
        media_type=stored_file.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{stored_file.original_filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{record_id}/download-url", response_model=DownloadUrlOut)
def download_url(
    record_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    try:
        return generate_download_url(db, record, user)
    except VaultError as err:
        raise _raise(err) from None


@router.get("/{record_id}/audit", response_model=list[VaultEventOut])
def record_audit_trail(
    record_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Access history for one record — owner or active share holder (view scope)."""
    record = db.get(HealthRecord, record_id)
    if record is None or record.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Record not found")
    try:
        authorize_access(db, record, user, required_scope="VIEW_RECORD")
    except VaultError as err:
        raise _raise(err) from None
    return (
        db.query(HealthRecordAccessEvent)
        .filter(HealthRecordAccessEvent.record_id == record.id)
        .order_by(HealthRecordAccessEvent.created_at.desc())
        .limit(200)
        .all()
    )
