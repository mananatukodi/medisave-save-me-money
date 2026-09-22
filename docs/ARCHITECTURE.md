# MediSave AI — Architecture

Monorepo: `backend/` (FastAPI) · `admin/` (React) · `mobile/` (Flutter) · `docs/`.

```
PATIENT APP (Flutter, authored)
        │  /api/v1 (HTTPS, JWT)
        ▼
FASTAPI BACKEND  ── AI SAFETY PIPELINE (consent → emergency screen → intent → validate → audit)
        │
        ├── PostgreSQL (SQLAlchemy 2.0 + Alembic)      [runtime REQUIRES POSTGRES]
        ├── AI provider abstraction (default: deterministic guidance engine; LLM REQUIRES INTEGRATION)
        └── ADMIN DASHBOARD (React+TS, SUPER_ADMIN, server-side RBAC)
```

## Backend layering

- `app/api/v1/` — routers (auth, users, ai, specialties, consents, feature-flags, emergency, admin)
- `app/security/` — bcrypt hashing, JWT (access 30 min / refresh 7 d), `require_roles()` RBAC dependency, audit helper
- `app/ai/` — `intents.py` (28 intents, te/en/hi keywords), `safety.py` (emergency/urgent screening, claim validator), `classifier.py` (deterministic), `engine.py` (pipeline), `providers.py` (LLM abstraction)
- `app/models/` — SQLAlchemy 2.0 models; `app/db/session.py` — engine/Base; `alembic/` — migrations
- `app/services/seed.py` — idempotent catalog seed (roles, 17 specialties, feature flags). **Never seeds fabricated providers/prices.**

## Key design decisions

1. **Emergency screening runs before the consent gate** — a user without AI_ACCESS consent still gets emergency guidance. Safety > flow (tested).
2. **Honest SOS**: events are created `REQUESTED`; no endpoint transitions to `CONFIRMED` without a real provider. Dispatch integration is `REQUIRES INTEGRATION`.
3. **No fabricated data**: seed contains only structural catalog data. Providers, medicines, prices require the Phase 3 verification workflow.
4. **AI provider abstraction**: `MEDISAVE_AI_PROVIDER=none` uses the deterministic guidance engine; any LLM must be implemented behind `providers.py` and stays behind the safety pipeline.
5. **Role checks are server-side** (`require_roles`); admin UI checks are cosmetic only.

## Rate limiting
The `slowapi` dependency is declared in the plan but **NOT IMPLEMENTED yet** — listed as a known gap; add per-IP limits on `/auth/*` and `/ai/chat` before public deployment.

## Offline (mobile)
See `OFFLINE_MODE.md`. `ApiClient.enqueueForRetry` queues failed POSTs; `flushQueue()` retries and never drops actions.
