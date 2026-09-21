"""MediSave AI FastAPI application (spec §22, §23, §40)."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import (
    admin,
    admin_partners,
    admin_pharmacy,
    admin_verification,
    ai,
    appointments,
    auth,
    consents,
    doctors,
    emergency,
    family,
    feature_flags,
    health_records,
    hospitals,
    medicines,
    orders,
    partners,
    pharmacies,
    providers,
    specialties,
    users,
)
from app.core.config import settings
from app.core.ratelimit import rate_limit_ai, rate_limit_auth, rate_limit_search
from app.db.session import SessionLocal

API_V1 = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="MediSave AI API",
        version="0.1.0",
        description=(
            "Patient-first healthcare ecosystem API. "
            "The AI Health Assistant is a navigation/safety layer — it is NOT a doctor."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix=API_V1, dependencies=[Depends(rate_limit_auth)])
    app.include_router(users.router, prefix=API_V1)
    app.include_router(ai.router, prefix=API_V1, dependencies=[Depends(rate_limit_ai)])
    app.include_router(specialties.router, prefix=API_V1)
    app.include_router(consents.router, prefix=API_V1)
    app.include_router(feature_flags.router, prefix=API_V1)
    app.include_router(emergency.router, prefix=API_V1)
    app.include_router(admin.router, prefix=API_V1)
    app.include_router(admin_verification.router, prefix=API_V1)
    app.include_router(doctors.router, prefix=API_V1)
    app.include_router(hospitals.router, prefix=API_V1)
    app.include_router(providers.router, prefix=API_V1)
    app.include_router(appointments.router, prefix=API_V1)
    app.include_router(medicines.router, prefix=API_V1, dependencies=[Depends(rate_limit_search)])
    app.include_router(pharmacies.router, prefix=API_V1, dependencies=[Depends(rate_limit_search)])
    app.include_router(pharmacies.self_router, prefix=API_V1)
    app.include_router(orders.router, prefix=API_V1)
    app.include_router(health_records.router, prefix=API_V1)
    app.include_router(family.router, prefix=API_V1, dependencies=[Depends(rate_limit_search)])
    app.include_router(admin_pharmacy.router, prefix=API_V1)
    # Phase 8: partner ecosystem
    app.include_router(partners.router, prefix=API_V1)
    app.include_router(partners.partner_router, prefix=API_V1)
    app.include_router(partners.lab_public_router, prefix=API_V1)
    app.include_router(partners.claims_public_router, prefix=API_V1)
    app.include_router(admin_partners.router, prefix=API_V1)

    @app.on_event("startup")
    def on_startup() -> None:
        # Dev convenience ONLY (never in prod): auto-create schema on SQLite so
        # local runs work without a migration step. Production uses Alembic:
        #   alembic upgrade head
        if not settings.is_production and settings.database_url.startswith("sqlite"):
            from app.db.session import Base, engine

            Base.metadata.create_all(engine)

        if settings.seed_on_startup:
            from app.services.seed import seed

            db = SessionLocal()
            try:
                seed(db)
            finally:
                db.close()

    # ---- Health checks (spec §40) ----
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "env": settings.env, "demo_mode": settings.demo_mode}

    @app.get("/ready")
    def ready() -> dict:
        checks: dict[str, str] = {}
        status = "ok"
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"
            status = "degraded"
        return {"status": status, "checks": checks}

    @app.get("/version")
    def version() -> dict:
        return {
            "name": "MediSave AI",
            "version": "0.1.0",
            "tagline": "Smart Healthcare. Better Care. Lower Cost.",
            "ai_provider": settings.ai_provider,
        }

    return app


app = create_app()
