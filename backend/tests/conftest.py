"""Pytest fixtures: isolated in-memory SQLite DB, seeded, with auth helpers."""

import os

# Must be set BEFORE app modules import settings.
os.environ.setdefault("MEDISAVE_ENV", "test")
os.environ.setdefault("MEDISAVE_SECRET_KEY", "test-only-secret-not-for-production")
os.environ.setdefault("MEDISAVE_DATABASE_URL", "sqlite:///./test-unused.db")
os.environ.setdefault("MEDISAVE_SEED_ON_STARTUP", "false")
os.environ.setdefault("MEDISAVE_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("MEDISAVE_DEMO_MODE", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models.user import Role, User, UserRole
from app.security.hashing import hash_password
from app.services.seed import seed


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    TestingSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    seed(session)  # roles + specialties + feature flags
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_user(
    db_session, email: str, password: str = "Password123!", roles: tuple[str, ...] = ("PATIENT",)
) -> User:
    user = User(
        full_name="Test User",
        email=email,
        password_hash=hash_password(password),
        primary_language="te",
    )
    db_session.add(user)
    db_session.flush()
    for role_id in roles:
        if db_session.get(Role, role_id) is None:
            db_session.add(Role(id=role_id, description=f"test role {role_id}"))
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    db_session.commit()
    return user


def login_headers(client, email: str, password: str = "Password123!") -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def patient_headers(client, db_session):
    make_user(db_session, "patient@example.com")
    return login_headers(client, "patient@example.com")


@pytest.fixture()
def admin_headers(client, db_session):
    make_user(db_session, "admin@example.com", roles=("SUPER_ADMIN",))
    return login_headers(client, "admin@example.com")


@pytest.fixture()
def doctor_headers(client, db_session):
    make_user(db_session, "doctor@example.com", roles=("DOCTOR",))
    return login_headers(client, "doctor@example.com")


@pytest.fixture()
def hospital_headers(client, db_session):
    make_user(db_session, "hospital-admin@example.com", roles=("HOSPITAL_ADMIN",))
    return login_headers(client, "hospital-admin@example.com")


@pytest.fixture()
def second_patient_headers(client, db_session):
    make_user(db_session, "patient2@example.com")
    return login_headers(client, "patient2@example.com")
