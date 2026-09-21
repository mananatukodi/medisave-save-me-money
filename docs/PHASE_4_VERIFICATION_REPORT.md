# Phase 4 Verification Report — Medicines, Pharmacy, Price Intelligence, Savings

Date: 2026-09-19 · Status: **PASS (verified)**

## 1. Scope
Medicine catalog (admin master data), pharmacy registration + SUPER_ADMIN
verification with immutable history, inventory with honest stock states,
versioned provenance-tracked prices with verification + expiration, MediSave
Savings Engine, medicine order state machine with immutable price snapshots,
prescription gating, AI medicine intents (9 new) with safe trilingual
guidance, admin dashboard pages, Flutter screens + te/en/hi localization.

## 2. Exact commands used
```
cd backend && .venv/Scripts/python -m pytest -p no:warnings --tb=no
cd backend && .venv/Scripts/python -m ruff check app tests scripts
cd backend && MEDISAVE_DATABASE_URL="postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave" .venv/Scripts/python -m alembic upgrade head
cd backend && MEDISAVE_DATABASE_URL="postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave" .venv/Scripts/python scripts/pg_check.py
cd backend && MEDISAVE_DATABASE_URL="postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave" MEDISAVE_DEMO_MODE=true .venv/Scripts/python scripts/smoke_test.py
cd admin && npm run build            # tsc -b && vite build
docker compose up -d postgres
```

## 3. Results

| Check | Result |
|---|---|
| Backend tests | **142 passed / 0 failed** (87 existing + 25 pharmacy/pricing/savings + 17 orders + 13 AI medicine) — collected 142, confirmed twice |
| Ruff | **PASS** (all checks passed) |
| Alembic | `2a34b8868e53` (head) — applied on SQLite scratch DB and real PostgreSQL; 39 tables total |
| PostgreSQL | Docker `postgres:16-alpine` on :5432; volume preserved; credentials aligned non-destructively (`ALTER USER`); **10 Phase 4 tables** present; **47 FKs**, **124 indexes** |
| Integrity (`pg_check.py`) | PASS ×5: double-booking index (P3), inventory uniqueness, price versioning (exactly one current row), order snapshot independent of catalog change, cleanup leaves zero fabricated rows |
| Orphan checks | 0 orphan order items / prices / inventory rows |
| HTTP smoke | **28/28 PASS** against PostgreSQL — includes honesty proofs: unverified-pharmacy price excluded; savings `INSUFFICIENT_DATA` rather than a fabricated number; Rx order pauses at `PRESCRIPTION_REQUIRED`; order 404 for non-owners; price-queue RBAC 403 |
| Admin | `tsc -b && vite build` **PASS** (241 kB bundle) |
| Flutter | Source authored (search/detail/order/my-orders/pharmacy screens, router, te/en/hi ARBs). **NOT COMPILED — Flutter SDK unavailable** |

## 4. Security / data-integrity review
- All authorization is server-side (`require_roles`, ownership checks, 404-not-403 for foreign orders).
- Verification status changes only via audited SUPER_ADMIN decisions writing immutable history rows.
- Price verification required before patient visibility; expiration sweep prevents stale "current" prices.
- Order price snapshots are immutable; catalog changes never rewrite history (verified in Postgres).
- Rate limiting: auth 10/min, AI 20/min, search 60/min per IP, `MEDISAVE_RATE_LIMIT_ENABLED` switch; smoke disables it explicitly via its documented config switch.
- Dev database cleaned of all smoke fixtures (medicines/pharmacies/prices/orders = 0); Phase 1–3 rows untouched.
- No secrets committed; `.env` git-ignored, only `.env.example` templates exist.

## 5. Production blockers (NOT IMPLEMENTED — do not treat as complete)
- Refresh-token rotation (jti scaffolded only)
- Payment gateway · Maps · SMS/WhatsApp · delivery integrations
- Real medicine database / external price feeds (catalog is empty until integrated)
- Real pharmacy/doctor verification document pipeline (upload + review) — REQUIRES INTEGRATION
- Prescription document upload & pharmacist verification service (state machine exists; document handling does not)
- Production PostgreSQL provisioning & multi-instance rate limiting (gateway/Redis)
- Flutter compilation (SDK missing)

## 6. Remaining TODOs
Scheduled price-expiration worker (endpoint exists, cron not wired), generic/brand substitution-request AI flow tests at HTTP level, admin savings analytics view, notification triggers on order events.
