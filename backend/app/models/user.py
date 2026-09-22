"""User, family members, and RBAC models (spec §4: server-side RBAC)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", String(40), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", String(80), ForeignKey("permissions.id"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # e.g. PATIENT, SUPER_ADMIN
    description: Mapped[str] = mapped_column(String(200), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. records:read
    description: Mapped[str] = mapped_column(String(200), default="")

    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(40), ForeignKey("roles.id"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    granted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="user_roles")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    primary_language: Mapped[str] = mapped_column(String(8), default="te")  # te | en | hi
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    roles: Mapped[list[UserRole]] = relationship(back_populates="user", cascade="all, delete-orphan")
    family_members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def role_ids(self) -> list[str]:
        return sorted(ur.role_id for ur in self.roles)


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # Python attr avoids shadowing sqlalchemy.orm.relationship; DB column stays "relationship".
    relationship_type: Mapped[str] = mapped_column("relationship", String(40))  # SPOUSE, CHILD, PARENT, OTHER
    date_of_birth: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO date
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="family_members")
