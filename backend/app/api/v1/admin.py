"""Admin endpoints (spec §32) — SUPER_ADMIN only, server-side RBAC enforced."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.ops import AuditLog, FeatureFlag
from app.models.pharmacy import MedicineOrder
from app.models.user import Role, User, UserRole
from app.schemas.common import AuditLogOut, FeatureFlagOut
from app.schemas.pharmacy import OrderOut
from app.schemas.providers import AppointmentOut
from app.security.deps import CurrentUser, record_audit, require_roles

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("SUPER_ADMIN"))],
)


class UserAdminOut(BaseModel):
    id: str
    full_name: str
    email: str
    is_active: bool
    roles: list[str] = Field(validation_alias="role_ids")

    model_config = {"from_attributes": True}


class RoleAssignRequest(BaseModel):
    role_id: str = Field(max_length=40)


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[User]:
    return db.query(User).order_by(User.created_at.desc()).offset(offset).limit(min(limit, 200)).all()


@router.post("/users/{user_id}/roles", response_model=UserAdminOut)
def assign_role(
    user_id: str,
    payload: RoleAssignRequest,
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    role = db.get(Role, payload.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    exists = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
        .first()
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="User already has this role")
    db.add(UserRole(user_id=user.id, role_id=role.id, granted_by=admin.id))
    db.commit()
    record_audit(
        db, action="ROLE_CHANGE", actor_user_id=admin.id, actor_role="SUPER_ADMIN",
        resource_type="user", resource_id=user.id, detail=f"granted role {role.id}",
    )
    db.commit()
    return user


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
def admin_list_flags(
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FeatureFlag]:
    return db.query(FeatureFlag).order_by(FeatureFlag.key.asc()).all()


@router.get("/appointments", response_model=list[AppointmentOut])
def admin_list_appointments(
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 50,
    offset: int = 0,
) -> list[Appointment]:
    return (
        db.query(Appointment)
        .order_by(Appointment.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/orders", response_model=list[OrderOut])
def admin_list_orders(
    admin: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[MedicineOrder]:
    """Medicine order oversight, including prescription-required states."""
    query = db.query(MedicineOrder).order_by(MedicineOrder.created_at.desc())
    if status:
        query = query.filter(MedicineOrder.status == status)
    return query.offset(offset).limit(min(limit, 200)).all()


@router.get("/vault/overview")
def vault_overview(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Governance metrics for the Health Vault.

    PRIVACY (Phase 5 spec §13): aggregate counts and security events only —
    no record titles, descriptions, filenames, or document contents. Admin is
    NOT a window into patient data; clinical access stays with owners and
    explicitly granted sharees.
    """
    from sqlalchemy import func

    from app.models.vault import (
        HealthRecord,
        HealthRecordAccessEvent,
        HealthRecordShare,
        StoredFile,
    )

    record_count = db.query(func.count(HealthRecord.id)).scalar() or 0
    file_count = db.query(func.count(StoredFile.id)).scalar() or 0
    storage_bytes = db.query(func.coalesce(func.sum(StoredFile.size_bytes), 0)).scalar()
    active_shares = (
        db.query(func.count(HealthRecordShare.id))
        .filter(HealthRecordShare.revoked_at.is_(None), HealthRecordShare.expires_at.is_(None))
        .scalar()
        or 0
    )
    active_shares += (
        db.query(func.count(HealthRecordShare.id))
        .filter(HealthRecordShare.revoked_at.is_(None), HealthRecordShare.expires_at > func.now())
        .scalar()
        or 0
    )
    event_rows = (
        db.query(HealthRecordAccessEvent)
        .order_by(HealthRecordAccessEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "records": record_count,
        "stored_files": file_count,
        "storage_bytes": int(storage_bytes or 0),
        "active_shares": active_shares,
        "recent_events": [
            {
                "id": str(ev.id),
                "action": ev.action,
                "result": ev.result,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in event_rows
        ],
    }


@router.get("/family/overview")
def family_overview(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Governance-only family metrics (Phase 6 spec §23): aggregate counts and
    audited family actions. No relationship names, no consent contents, no
    medical data — admin never becomes a window into patient/family data."""
    from sqlalchemy import func

    from app.models.family import FamilyRelationship
    from app.models.ops import AuditLog

    def count(status: str) -> int:
        return (
            db.query(func.count(FamilyRelationship.id))
            .filter(FamilyRelationship.status == status)
            .scalar()
            or 0
        )

    events = (
        db.query(AuditLog)
        .filter(
            (AuditLog.resource_type == "family") | (AuditLog.action.like("FAMILY%"))
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    denied = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.action == "FAMILY_RECORD_ACCESS_DENIED")
        .scalar()
        or 0
    )
    return {
        "active_relationships": count("ACTIVE"),
        "pending_invitations": count("INVITED"),
        "declined_invitations": count("DECLINED"),
        "expired_invitations": count("EXPIRED"),
        "revoked_relationships": count("REVOKED"),
        "access_denied_events": int(denied),
        "recent_events": [
            {
                "id": str(ev.id),
                "action": ev.action,
                "outcome": ev.outcome,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in events
        ],
    }


@router.get("/emergency/overview")
def emergency_overview(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Emergency governance metrics (Phase 7): operational aggregates only.
    No event notes, no coordinates, no clinical content — admin oversight
    never becomes a window into patient emergencies."""
    from sqlalchemy import func

    from app.models.emergency import (
        EmergencyEvent,
        EmergencyHandoff,
        EmergencyNotification,
        EmergencyProviderEvent,
    )

    def event_count(status: str) -> int:
        return (
            db.query(func.count(EmergencyEvent.id))
            .filter(EmergencyEvent.status == status)
            .scalar()
            or 0
        )

    notification_counts = dict(
        db.query(EmergencyNotification.status, func.count(EmergencyNotification.id))
        .group_by(EmergencyNotification.status)
        .all()
    )
    handoff_counts = dict(
        db.query(EmergencyHandoff.status, func.count(EmergencyHandoff.id))
        .group_by(EmergencyHandoff.status)
        .all()
    )
    ambulance_events = (
        db.query(func.count(EmergencyProviderEvent.id))
        .filter(EmergencyProviderEvent.action == "DISPATCH_REQUESTED")
        .scalar()
        or 0
    )
    ambulance_failed = (
        db.query(func.count(EmergencyProviderEvent.id))
        .filter(
            EmergencyProviderEvent.action == "DISPATCH_REQUESTED",
            EmergencyProviderEvent.status == "NOT_CONFIGURED",
        )
        .scalar()
        or 0
    )
    denied = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.resource_type == "emergency",
            AuditLog.outcome == "DENIED",
        )
        .scalar()
        or 0
    )
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "emergency")
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    return {
        "active_emergencies": sum(
            event_count(s)
            for s in ("REQUESTED", "ALERTING", "CONTACTING", "ACTIVE", "HANDOFF_PENDING")
        ),
        "status_counts": {
            s: event_count(s)
            for s in (
                "REQUESTED", "ALERTING", "CONTACTING", "ACTIVE", "HANDOFF_PENDING",
                "HANDED_OFF", "RESOLVED", "CANCELLED", "FALSE_ALARM", "FAILED",
            )
        },
        "notification_delivery": {
            "QUEUED": int(notification_counts.get("QUEUED", 0)),
            "SENT": int(notification_counts.get("SENT", 0)),
            "DELIVERED": int(notification_counts.get("DELIVERED", 0)),
            "FAILED": int(notification_counts.get("FAILED", 0)),
        },
        "handoff_status": {
            "REQUESTED": int(handoff_counts.get("HANDOFF_REQUESTED", 0)),
            "ACCEPTED": int(handoff_counts.get("HANDOFF_ACCEPTED", 0)),
            "REJECTED": int(handoff_counts.get("HANDOFF_REJECTED", 0)),
            "EXPIRED": int(handoff_counts.get("HANDOFF_EXPIRED", 0)),
            "COMPLETED": int(handoff_counts.get("HANDOFF_COMPLETED", 0)),
        },
        "ambulance_provider": {
            "configured": False,  # honest until a real provider is wired
            "dispatch_requests": int(ambulance_events),
            "not_configured_attempts": int(ambulance_failed),
        },
        "security_denied_events": int(denied),
        "recent_events": [
            {
                "id": str(ev.id),
                "action": ev.action,
                "outcome": ev.outcome,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in recent
        ],
    }



