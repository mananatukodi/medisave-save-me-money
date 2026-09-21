"""Family accounts & caregiver access endpoints (Phase 6).

Every endpoint resolves authorization server-side from the token — client
supplied IDs/scopes are never trusted. Sensitive actions are audited.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.family import FamilyAccessConsent, FamilyRelationship
from app.models.ops import AuditLog
from app.schemas.family import (
    ConsentOut,
    ConsentPut,
    InvitationCreate,
    InvitationOut,
    RelationshipOut,
)
from app.security.deps import CurrentUser
from app.services import family_service
from app.services.family_service import FamilyError

router = APIRouter(prefix="/family", tags=["family"])


def _family_error(err: FamilyError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=str(err))


@router.post("/invitations", response_model=InvitationOut, status_code=201)
def create_invitation(
    payload: InvitationCreate,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> InvitationOut:
    if payload.member_user_id is None and not payload.invited_email:
        raise HTTPException(status_code=422, detail="invited_email is required for email invitations")
    try:
        rel, token = family_service.create_invitation(
            db,
            owner=current_user,
            display_name=payload.display_name,
            relationship_type=payload.relationship_type,
            invited_email=payload.invited_email,
            member_user_id=payload.member_user_id,
        )
    except FamilyError as err:
        raise _family_error(err) from None
    out = InvitationOut.model_validate(rel)
    out.invitation_token = token  # shown exactly once; never persisted or logged
    return out


@router.get("/invitations", response_model=list[RelationshipOut])
def list_invitations(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FamilyRelationship]:
    """Invitations I sent (owner view) — never exposes token material."""
    return (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.owner_user_id == current_user.id,
            FamilyRelationship.status == "INVITED",
        )
        .order_by(FamilyRelationship.created_at.desc())
        .all()
    )


@router.get("/invitations/received", response_model=list[RelationshipOut])
def list_received_invitations(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FamilyRelationship]:
    """Email invitations addressed to my account that I can accept/decline."""
    return (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.invited_email == current_user.email.lower(),
            FamilyRelationship.status == "INVITED",
        )
        .order_by(FamilyRelationship.created_at.desc())
        .all()
    )


@router.post("/invitations/{relationship_id}/accept", response_model=RelationshipOut)
def accept_invitation(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyRelationship:
    try:
        return family_service.accept_invitation(
            db, invitee=current_user, relationship_id=relationship_id
        )
    except FamilyError as err:
        raise _family_error(err) from None


@router.post("/invitations/{relationship_id}/decline", response_model=RelationshipOut)
def decline_invitation(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyRelationship:
    try:
        return family_service.decline_invitation(
            db, invitee=current_user, relationship_id=relationship_id
        )
    except FamilyError as err:
        raise _family_error(err) from None


@router.get("/relationships", response_model=list[RelationshipOut])
def list_relationships(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FamilyRelationship]:
    """Relationships where I am the owner or the member."""
    return (
        db.query(FamilyRelationship)
        .filter(
            (FamilyRelationship.owner_user_id == current_user.id)
            | (FamilyRelationship.member_user_id == current_user.id)
        )
        .order_by(FamilyRelationship.created_at.desc())
        .all()
    )


@router.get("/relationships/{relationship_id}", response_model=RelationshipOut)
def get_relationship(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyRelationship:
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None or (
        rel.owner_user_id != current_user.id and rel.member_user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Relationship not found")
    return rel


@router.post("/relationships/{relationship_id}/revoke", response_model=RelationshipOut)
def revoke_relationship(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyRelationship:
    try:
        return family_service.revoke_relationship(
            db, actor=current_user, relationship_id=relationship_id
        )
    except FamilyError as err:
        raise _family_error(err) from None


@router.get("/relationships/{relationship_id}/consent", response_model=list[ConsentOut])
def get_consent(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FamilyAccessConsent]:
    rel = db.get(FamilyRelationship, relationship_id)
    if rel is None or (
        rel.owner_user_id != current_user.id and rel.member_user_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="Relationship not found")
    return (
        db.query(FamilyAccessConsent)
        .filter(FamilyAccessConsent.relationship_id == rel.id)
        .order_by(FamilyAccessConsent.created_at.desc())
        .all()
    )


@router.put("/relationships/{relationship_id}/consent", response_model=ConsentOut)
def put_consent(
    relationship_id: str,
    payload: ConsentPut,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyAccessConsent:
    try:
        return family_service.grant_consent(
            db,
            owner=current_user,
            relationship_id=relationship_id,
            scopes=payload.scopes,
            category_filter=payload.category_filter,
            purpose=payload.purpose,
            expires_in_days=payload.expires_in_days,
        )
    except FamilyError as err:
        raise _family_error(err) from None


@router.delete("/relationships/{relationship_id}/consent", response_model=ConsentOut)
def delete_consent(
    relationship_id: str,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> FamilyAccessConsent:
    try:
        return family_service.revoke_consent(
            db, owner=current_user, relationship_id=relationship_id
        )
    except FamilyError as err:
        raise _family_error(err) from None


@router.get("/access-granted-to-me", response_model=list[RelationshipOut])
def access_granted_to_me(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[FamilyRelationship]:
    return (
        db.query(FamilyRelationship)
        .filter(
            FamilyRelationship.member_user_id == current_user.id,
            FamilyRelationship.status == "ACTIVE",
        )
        .order_by(FamilyRelationship.accepted_at.desc())
        .all()
    )


@router.get("/access-history")
def access_history(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    """Family-related audit rows where I am the actor (owner or member).
    Covers both relationship events (resource_type=family) and family-scoped
    record access events (action FAMILY_* written by the vault service)."""
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_user_id == current_user.id,
            (AuditLog.resource_type == "family") | (AuditLog.action.like("FAMILY%")),
        )
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "outcome": row.outcome,
            "resource_id": row.resource_id,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
