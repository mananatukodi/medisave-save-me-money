# MediSave AI — Deployment

> Status: development-ready, **not yet production-deployed**. Rate limiting is implemented
> in-process (single worker); multi-instance deployments still need a gateway/Redis limiter.

## Docker (local development, Phase 3)

```bash
cp .env.example .env          # then edit values — never commit .env
docker compose up -d --build  # postgres + backend (migrations auto-apply)
# API on http://localhost:8000 · OpenAPI at /docs

docker compose down -v        # stop and remove the volume
```

Postgres-only mode (run the backend from the host):
```bash
docker compose up -d postgres
cd backend
MEDISAVE_DATABASE_URL=postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave \
  alembic upgrade head
MEDISAVE_DATABASE_URL=postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave \
  uvicorn app.main:app --reload
```

Verification scripts against the live DB:
```bash
MEDISAVE_DATABASE_URL=postgresql+psycopg://... python scripts/pg_check.py    # double-booking proof
MEDISAVE_DATABASE_URL=postgresql+psycopg://... python scripts/smoke_test.py  # 14 HTTP checks
```

## Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
export MEDISAVE_ENV=prod
export MEDISAVE_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(64))')"
export MEDISAVE_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/medisave
export MEDISAVE_DEMO_MODE=false
export MEDISAVE_CORS_ORIGINS='["https://admin.yourdomain"]'
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Run behind a reverse proxy (nginx/Caddy/ALB) that terminates **HTTPS**, adds HSTS, and enables
gzip/brotli. Health endpoints for load balancers: `/health`, `/ready`, `/version`.

## Admin dashboard

```bash
cd admin && npm ci && npm run build   # outputs dist/
```
Serve `dist/` statically behind HTTPS; proxy `/api` to the backend (same origin simplifies CORS).

## Mobile

`flutter build apk --dart-define=MEDISAVE_API_BASE_URL=https://api.yourdomain` (requires Flutter SDK).

## CI

`.github/workflows/ci.yml` runs backend pytest and the admin typecheck+build on every push.

## Pre-production checklist

- [ ] PostgreSQL provisioned; `alembic upgrade head` succeeds against it
- [ ] `MEDISAVE_SECRET_KEY` set from a secret manager (not committed)
- [ ] Rate limiting active on `/auth/*` and `/ai/chat`
- [ ] HTTPS + HSTS at the proxy; CORS allow-list matches deployed origins
- [ ] `MEDISAVE_DEMO_MODE=false` and demo seeds disabled
- [ ] Backup + restore for the database verified
- [ ] Audit-log retention policy agreed
