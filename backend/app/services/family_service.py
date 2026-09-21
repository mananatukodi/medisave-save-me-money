"""Family accounts & caregiver access service (Phase 6).

SECURITY RULES:
- Invitation tokens: secrets.token_urlsafe(32), stored as SHA-256 hash only,
  24 h expiry, single use. Raw tokens are returned once to the inviter and
  never logged.
- A relationship grants ZERO access. Access = ACTIVE relationship + ACTIVE
  FamilyAccessConsent with the required scope, re-checked on every request.
- All grants/updates/revocations are owner-only and audited.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.family import (
    FAMILY_SCOPES,
    INVITATION_TTL_HOURS,
    RELATIONSHIP_TYPES,
    FamilyAccessConsent,
    FamilyRelationship,
)
from app.models.ops import AuditLog


class FamilyError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalize to aware-UTC for comparisons."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _audit(
    db: Session,
    *,
    actor_user_id: str,
    action: str,
    resource_id: str,
    detail: str = "",
    outcome: str = "SUCCESS",
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            actor_role="PATIENT",
            action=action,
            resource_type="family",
            resource_id=resource_id,
            outcome=outcome,
            detail=detail[:500],
        )
    )


# ------------------------------------------------------------- invitations

def create_invitation(
    db: Session,
    *,
    owner,
    display_name: str,
    relationship_type: str,
    invited_email: str | None = None,
    member_user_id: str | None = None,
) -> tuple[FamilyRelationship, str]:
    """Create an INVITED relationship. Returns (relationship, raw_token).

    The raw token is shown once to the inviter (delivered out-of-band in
    production); only its SHA-256 hash is persisted.
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        raise FamilyError(f"relationship_type must be one of: {', '.join(RELATIONSHIP_TYPES)}", 422)
    if not display_name.strip():
        raise FamilyError("display_name is required", 422)
    if member_user_id is not None:
        if member_user_id == owner.id:
            raise FamilyError("You cannot invite yourself", 422)
        existing = (
            db.query(FamilyRelationship)
            .filter(
                FamilyRelationship.owner_user_id == owner.id,
                FamilyRelationship.member_user_id == member_user_id,
                FamilyRelationship.status == "ACTIVE",
            )
            .first()
        )
        if existing is not None:
            raise FamilyError("An active relationship with this member already exists", 409)
    token = secrets.token_urlsafe(32)
    rel = FamilyRelationship(
        owner_user_id=owner.id,
        member_user_id=member_user_id,
        display_name=display_name.strip()[:120],
        relationship_type=relationship_type,
        invited_email=(invited_email or "").strip().lower() or None,
        status="INVITED",
        invitation_token_hash=hash_token(token),
        invitation_expires_at=datetime.now(UTC) + timedelta(hours=INVITATION_TTL_HOURS),
    )
    db.add(rel)
    db.flush()
    _audit(
        db,
        actor_user_id=owner.id,
        action="FAMILY_INVITATION_CREATED",
        resource_id=rel.id,
        detail=f"type={relationship_type} to={'existing-user' if member_user_id else 'email-invite'}",
    )
    db.commit()
    return rel, token


def _expire_stale(db: Session, rel: FamilyRelationship) -> None:
    expires = _aware(rel.invitation_expires_at)
    if rel.status == "INVITED" and expires is not None and expires <= datetime.now(UTC):
        rel.status = "EXPIRED"


def accept_invitation(db: Session, *, invitee, relationship_id: str) -> FamilyRelationship:
    """Accept an invitation. Requires the invitee account to match the invited
    email (existing-user invites) or any authenticated user (email invites):
    the relationship is bound to the accepting account at accept time."""
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None:
        raise FamilyError("Invitation not found", 404)
    _expire_stale(db, rel)
    if rel.status == "EXPIRED":
        raise FamilyError("Invitation has expired", 410)
    if rel.status != "INVITED":
        raise FamilyError(f"Invitation is not pending (status={rel.status})", 409)
    if rel.invited_email and rel.member_user_id is None:
        if rel.invited_email != invitee.email.lower():
            raise FamilyError("This invitation was issued to a different email address", 403)
    elif rel.member_user_id is not None and rel.member_user_id != invitee.id:
        raise FamilyError("This invitation was issued to a different user", 403)
    rel.member_user_id = invitee.id
    rel.status = "ACTIVE"
    rel.accepted_at = datetime.now(UTC)
    _audit(
        db,
        actor_user_id=invitee.id,
        action="FAMILY_INVITATION_ACCEPTED",
        resource_id=rel.id,
        detail=f"owner={rel.owner_user_id} type={rel.relationship_type}",
    )
    db.commit()
    return rel


def decline_invitation(db: Session, *, invitee, relationship_id: str) -> FamilyRelationship:
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None:
        raise FamilyError("Invitation not found", 404)
    _expire_stale(db, rel)
    if rel.status != "INVITED":
        raise FamilyError(f"Invitation is not pending (status={rel.status})", 409)
    if rel.member_user_id is not None and rel.member_user_id != invitee.id:
        raise FamilyError("This invitation was issued to a different user", 403)
    rel.status = "DECLINED"
    rel.declined_at = datetime.now(UTC)
    _audit(
        db,
        actor_user_id=invitee.id,
        action="FAMILY_INVITATION_DECLINED",
        resource_id=rel.id,
    )
    db.commit()
    return rel


def get_by_token(db: Session, token: str) -> FamilyRelationship | None:
    return (
        db.query(FamilyRelationship)
        .filter(FamilyRelationship.invitation_token_hash == hash_token(token))
        .first()
    )


# ------------------------------------------------------- relationship ops

def revoke_relationship(db: Session, *, actor, relationship_id: str) -> FamilyRelationship:
    """Owner revokes a member, or member self-removes. Immediate."""
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None or (
        rel.owner_user_id != actor.id and rel.member_user_id != actor.id
    ):
        raise FamilyError("Relationship not found", 404)
    if rel.status not in ("INVITED", "ACTIVE"):
        raise FamilyError(f"Relationship is not revocable (status={rel.status})", 409)
    rel.status = "REVOKED"
    rel.revoked_at = datetime.now(UTC)
    for consent in (
        db.query(FamilyAccessConsent)
        .filter(
            FamilyAccessConsent.relationship_id == rel.id,
            FamilyAccessConsent.revoked_at.is_(None),
        )
        .all()
    ):
        consent.revoked_at = rel.revoked_at
    _audit(
        db,
        actor_user_id=actor.id,
        action="FAMILY_RELATIONSHIP_REVOKED",
        resource_id=rel.id,
        detail="side=owner" if rel.owner_user_id == actor.id else "side=member(self-remove)",
    )
    db.commit()
    return rel


# --------------------------------------------------------------- consent

def validate_scopes(scopes: list[str]) -> list[str]:
    cleaned = [s.strip().upper() for s in scopes if s.strip()]
    invalid = [s for s in cleaned if s not in FAMILY_SCOPES]
    if invalid:
        raise FamilyError(f"Unknown scopes: {', '.join(invalid)}", 422)
    return sorted(set(cleaned))


def grant_consent(
    db: Session,
    *,
    owner,
    relationship_id: str,
    scopes: list[str],
    category_filter: list[str] | None = None,
    purpose: str = "",
    expires_in_days: int | None = None,
) -> FamilyAccessConsent:
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None or rel.owner_user_id != owner.id:
        raise FamilyError("Relationship not found", 404)
    if rel.status != "ACTIVE":
        raise FamilyError("Consent requires an ACTIVE relationship", 409)
    cleaned = validate_scopes(scopes)
    if not cleaned:
        raise FamilyError("At least one scope is required", 422)
    # Revoke any previous active consent (single active consent per relationship).
    for old in (
        db.query(FamilyAccessConsent)
        .filter(
            FamilyAccessConsent.relationship_id == rel.id,
            FamilyAccessConsent.revoked_at.is_(None),
        )
        .all()
    ):
        old.revoked_at = datetime.now(UTC)
    consent = FamilyAccessConsent(
        relationship_id=rel.id,
        scopes=",".join(cleaned),
        category_filter=",".join(c.strip().upper() for c in (category_filter or []) if c.strip()),
        purpose=purpose[:500],
        granted_by=owner.id,
        expires_at=(
            datetime.now(UTC) + timedelta(days=expires_in_days)
            if expires_in_days
            else None
        ),
    )
    db.add(consent)
    db.flush()
    _audit(
        db,
        actor_user_id=owner.id,
        action="FAMILY_CONSENT_GRANTED",
        resource_id=rel.id,
        detail=f"scopes={','.join(cleaned)} categories={consent.category_filter or 'ALL'}",
    )
    db.commit()
    return consent


def revoke_consent(db: Session, *, owner, relationship_id: str) -> FamilyAccessConsent:
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None or rel.owner_user_id != owner.id:
        raise FamilyError("Relationship not found", 404)
    consent = (
        db.query(FamilyAccessConsent)
        .filter(
            FamilyAccessConsent.relationship_id == rel.id,
            FamilyAccessConsent.revoked_at.is_(None),
        )
        .order_by(FamilyAccessConsent.created_at.desc())
        .first()
    )
    if consent is None:
        raise FamilyError("No active consent for this relationship", 404)
    consent.revoked_at = datetime.now(UTC)
    _audit(
        db,
        actor_user_id=owner.id,
        action="FAMILY_CONSENT_REVOKED",
        resource_id=rel.id,
        detail=f"scopes={consent.scopes}",
    )
    db.commit()
    return consent


def active_consent(db: Session, relationship_id: str) -> FamilyAccessConsent | None:
    consent = (
        db.query(FamilyAccessConsent)
        .filter(
            FamilyAccessConsent.relationship_id == relationship_id,
            FamilyAccessConsent.revoked_at.is_(None),
        )
        .order_by(FamilyAccessConsent.created_at.desc())
        .first()
    )
    if consent is None or not consent.is_active:
        return None
    return consent


def relationship_for_member(
    db: Session, *, member_user_id: str, owner_user_id: str
) -> FamilyRelationship | None:
    rel = (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == owner_user_id,
            FamilyRelationship.member_user_id == member_user_id,
            FamilyRelationship.status == "ACTIVE",
        )
        .first()
    )
    return rel
