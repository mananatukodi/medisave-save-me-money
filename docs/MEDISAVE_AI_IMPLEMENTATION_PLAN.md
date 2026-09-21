# MediSave AI — Implementation Plan

> "Your Health, Our Priority. Your Money, Our Savings."
> Tagline: **Smart Healthcare. Better Care. Lower Cost.**

**Document status:** Living plan. Updated at the end of every implementation task (spec §53, §55).

---

## 1. Repository Inspection Report (per spec §53)

Inspected: 2026-09-19. Result: **GREENFIELD repository.**

| # | Area | Finding |
|---|------|---------|
| 1 | Complete directory tree | Empty — only `.freebuff/` config and `.git` with **zero commits** |
| 2 | Frontend architecture | None |
| 3 | Backend architecture | None |
| 4 | Database architecture | None |
| 5 | Authentication status | None |
|  access | Existing APIs | None |
| 7 | Existing AI functionality | None |
| 8 | Existing UI/screens | None |
| 9 | Existing integrations | None |
| 10 | Environment configuration | None (no `.env` / `.env.example`) |
| 11 | Build status | Nothing to build |
| 12 | Test status | No tests |
| 13 | Missing dependencies | Flutter SDK, Dart SDK, PostgreSQL server/client not installed on this machine |
| 14 | Security issues | None (no code) |
| 15 | Technical debt | None |
| 16 | Missing MediSave AI modules | **All 37 core modules** (expected for greenfield) |

**Conclusion:** There is no existing working functionality to preserve. The "do not rewrite blindly" rule is satisfied trivially; we build incrementally, phase by phase, per spec §49.

### 1.1 Toolchain reality check (honest assessment, spec §54)

| Tool | Status | Impact |
|------|--------|--------|
| Python 3.13.5 + pip 25.1.1 | ✅ available | Backend fully implementable and testable |
| Node 24.20.0 + npm 11.19.0 | ✅ available | Admin dashboard fully implementable, buildable, type-checkable |
| Flutter / Dart SDK | ❌ not installed | Flutter code will be **authored but not compiled locally**. Marked `REQUIRES FLUTTER SDK` |
| PostgreSQL server | ❌ not installed locally | DB layer authored against SQLAlchemy 2.0 ORM; runtime verification `REQUIRES POSTGRES`. SQLite used **only** for the automated test suite |

---

## 2. Preserved Existing Functionality

None — greenfield. Nothing to preserve; nothing will be blindly overwritten (empty repo).

---

## 3. Target Architecture

```
medisave-ai/
├── backend/            Python 3.13 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL
├── admin/              React 19 + TypeScript + Vite admin dashboard
├── mobile/             Flutter patient app (Riverpod + GoRouter + Dio)
├── docs/               Architecture, API, DB, security, AI safety, deployment docs
├── .github/workflows/  CI: backend tests, admin build, audit checks
└── README.md
```

### 3.1 Backend layout (spec §22)

```
backend/
  app/
    api/v1/            routers: auth, users, ai, specialties, ...
    core/              config, logging, errors, rate limiting
    db/                base, session, seeds
    models/            SQLAlchemy ORM models
    schemas/           Pydantic v2 schemas
    security/          jwt, hashing, rbac dependency
    ai/                intent classifier, safety pipeline, structured responses
    services/          business logic
    utils/             helpers
  tests/               pytest suite
  alembic/             migrations
  alembic.ini
  pyproject.toml
  .env.example
```

### 3.2 API versioning (spec §23)

All endpoints under `/api/v1/`. OpenAPI served at `/docs`.

### 3.3 Mobile layout (spec §24)

```
mobile/lib/
  core/       theme, constants, network, storage, utils
  config/     app_config, feature flags client
  routing/    GoRouter configuration
  l10n/       app_en.arb, app_te.arb, app_hi.arb
  features/   auth, home, ai, emergency, doctors, hospitals, specialties,
              eye_care, dental_care, pharmacy, medicines, records,
              prescriptions, labs, insurance, appointments, payments,
              family, notifications, support, profile
```

---

## 4. Required Changes / Missing Functionality

Everything (greenfield). Grouped into phases per spec §49:

### PHASE 1 — FOUNDATION
- [x] Repository architecture (monorepo: backend / admin / mobile / docs)
- [x] Auth: JWT access + refresh tokens, bcrypt password hashing
- [x] RBAC: 10 roles (PATIENT … SUPER_ADMIN), server-side dependency `require_roles(...)`
- [x] Database: SQLAlchemy 2.0 models + Alembic migration (users, roles, consents, audit_logs, specialties, feature_flags, ai tables)
- [x] API foundation: `/api/v1/auth`, `/api/v1/users/me`, `/api/v1/specialties`, `/api/v1/consents`, `/api/v1/feature-flags`, `/api/v1/admin/*`
- [x] Flutter foundation: pubspec, theme (brand colors), l10n (te/en/hi), GoRouter, core screens
- [x] CI/testing: pytest suite; GitHub Actions workflow
- [x] Security foundation: password policy, token expiry, audit logging, no secrets in repo

### PHASE 2 — AI HEALTH ASSISTANT
- [x] AI sessions + messages tables (consent-gated)
- [x] Intent classification: 28 intents from spec §10
- [x] Safety pipeline: emergency screening → red flags → structured response (spec §11 schema)
- [x] Navigation actions (e.g., navigate to Eye Care, SOS, doctor search)
- [x] Consent gate (`AI_ACCESS` consent required before AI use)
- [x] Audit logging of AI interactions
- [x] AI provider abstraction (`NullProvider` = honest "guidance engine", no LLM call)
- [x] AI safety tests (emergency detection, disclaimers, no certainty claims)

### PHASE 3 — HEALTHCARE ACCESS — ✅ IMPLEMENTED + TESTED
- [x] Specialty catalog seeded (17 specialties incl. EYE_CARE, DENTAL_CARE)
- [x] Specialty service catalog + verified-price structure (`verificationStatus`, `source`, `lastUpdated`)
- [x] Doctor registration (DOCTOR role) + 5-state verification workflow with immutable history + audit (PENDING/UNDER_REVIEW/VERIFIED/REJECTED/SUSPENDED)
- [x] Hospital registration (HOSPITAL_ADMIN role) + verification workflow; emergency advertised only when separately verified
- [x] Multi-specialty provider links (spec §4)
- [x] Provider services with provider-declared (UNVERIFIED) prices; verified prices only via verification data
- [x] Availability engine: weekly rules, slot computation, blocks/holidays, server-side slot validation
- [x] Appointment state machine (REQUESTED/CONFIRMED/RESCHEDULED/CANCELLED/COMPLETED/NO_SHOW) with transition rules + patient/provider RBAC
- [x] Double-booking prevention: in-process check + DB partial unique index — proven against real PostgreSQL
- [x] Rate limiting added (in-process; single-worker scope documented)
- [x] Docker: postgres + backend compose stack; migrations verified on PostgreSQL 16
- [x] Admin: verification queue UI, doctors/hospitals/specialties/appointments pages
- [x] Flutter: doctor search/profile, hospital search, booking flow, my appointments (AUTHORED — build REQUIRES FLUTTER SDK)

### PHASE 4 — MEDICINES & SAVINGS — *NOT IMPLEMENTED (requires pharmacy integrations)*

### PHASE 5 — HEALTH VAULT — *NOT IMPLEMENTED (requires object storage)*

### PHASE 6 — INSURANCE — *NOT IMPLEMENTED (requires insurer integrations)*

### PHASE 7 — EMERGENCY SOS — *backend event model exists; dispatch integration REQUIRES INTEGRATION (marked DEMO)*

### PHASE 8 — PARTNER ECOSYSTEM (portals) — *NOT IMPLEMENTED*

### PHASE 9 — SCALE — *NOT IMPLEMENTED*

---

## 5. Dependencies

Backend (declared in `backend/pyproject.toml`):
`fastapi`, `uvicorn`, `sqlalchemy>=2.0`, `alembic`, `pydantic`, `pydantic-settings`, `psycopg[binary]`, `passlib[bcrypt]`, `pyjwt`, `python-multipart`, `slowapi`, `httpx`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`

Admin: `react`, `react-dom`, `react-router-dom`, `typescript`, `vite`, `@tanstack/react-query`, `axios`

Mobile (`mobile/pubspec.yaml`): `flutter_riverpod`, `go_router`, `dio`, `flutter_secure_storage`, `intl`, `flutter_localizations`, `shared_preferences`

**Mobile fonts:** Poppins / Noto Sans Telugu / Noto Sans Devanagari — `REQUIRES FONT FILES` (not committed here; loading wired via `pubspec.yaml` and `ThemeExtension`).

---

## 6. Database Migrations

- Single initial Alembic migration `0001_initial_core.py` covering: `users`, `roles`, `permissions`, `user_roles`, `family_members`, `consents`, `ai_sessions`, `ai_messages`, `ai_events`, `specialties`, `specialty_services`, `provider_specialties` (structural), `audit_logs`, `feature_flags`, `system_settings`, `emergency_events`, `emergency_contacts`.
- Runtime verification against real PostgreSQL: `REQUIRES POSTGRES` (tests run on SQLite in-memory).
- All future schema changes require new Alembic revision. Never edit an applied migration.

## 7. API Changes

Versioned under `/api/v1/`. Additive changes only within v1. Breaking changes → `/api/v2/`.

## 8. UI Changes

- Flutter patient app scaffold with brand theme and Telugu-first localization.
- React admin dashboard shell with role-aware navigation and persistent DEMO banner.
- DEMO/SAMPLE/NOT REAL labeling enforced: any screen backed by seeded demo data must render the `DemoBanner` component / `DemoLabel` widget.

## 9. Testing Requirements (spec §45)

| Suite | Framework | Status |
|-------|-----------|--------|
| Backend unit + API tests | pytest + httpx ASGI | ✅ implemented, must stay green |
| RBAC tests | pytest (401/403 scenarios) | ✅ implemented |
| AI safety tests | pytest (emergency screening, disclaimer presence) | ✅ implemented |
| Consent-gate tests | pytest | ✅ implemented |
| Payment state tests | pytest (state machine unit tests) | 🔜 planned |
| Localization tests | Flutter `flutter test` | 🔜 REQUIRES FLUTTER SDK |
| Widget/integration tests | Flutter | 🔜 REQUIRES FLUTTER SDK |
| Security tests (dep audit) | `pip-audit`, `npm audit` | ✅ in CI plan |

## 10. Security Requirements (spec §36)

- JWT access (30 min) + refresh (7 d) tokens, bcrypt hashing, never store raw cards.
- Server-side RBAC on every protected route; frontend checks are cosmetic only.
- Audit logging for login, consent change, AI interactions, admin changes.
- Rate limiting via `slowapi` on auth + AI endpoints.
- Secrets only via environment variables; `.env` git-ignored; `.env.example` committed.
- Demo/production data isolation: demo seed endpoints flagged and labeled.

## 11. Honest Status Labels (spec §54)

| Capability | Status |
|-----------|--------|
| Auth, RBAC, consents, audit, specialties, AI guidance engine | ✅ IMPLEMENTED + TESTED (unit/API level) |
| Providers + verification + availability + appointments (Phase 3) | ✅ IMPLEMENTED + TESTED (87 pytest + 14/14 live smoke on PostgreSQL 16) |
| Double-booking prevention | ✅ VERIFIED against real PostgreSQL (partial unique index; `scripts/pg_check.py`) |
| Rate limiting | ✅ IMPLEMENTED (in-process, auth 10/min + AI 20/min per IP; multi-instance needs gateway/Redis) |
| Flutter app source | ✅ AUTHORED through Phase 3 — build REQUIRES FLUTTER SDK |
| Admin dashboard (incl. verification queue) | ✅ AUTHORED + builds clean (vite build) |
| PostgreSQL runtime | ✅ VERIFIED via docker compose (PostgreSQL 16, Alembic migrations applied) |
| Payment gateway | REQUIRES INTEGRATION (abstraction + DEMO provider only) |
| SMS / Email / Push | REQUIRES INTEGRATION |
| Maps | REQUIRES INTEGRATION |
| LLM provider for conversational AI | REQUIRES INTEGRATION (guidance engine works without it) |
| Emergency dispatch | REQUIRES INTEGRATION — status stays REQUESTED until a provider confirms; never fabricate |
| Real doctors / hospitals / medicine prices | Requires the implemented verification workflow to be exercised by real providers — no fabricated data shipped |

---

## 12. Next Steps

1. Phase 5: health records storage abstraction (S3-compatible signed URLs).
2. Hospital-side services + availability (hospital admins currently manage profiles only).
3. Real doctor/pharmacy document upload for verification (object storage) + document review UI.
4. Scheduled price-expiration worker + refresh-token rotation.
5. Install Flutter SDK to unlock the mobile build + widget/localization tests.

## Phase 4 status (2026-09-19) — COMPLETE (verified)

Medicine catalog (admin master data only, no fabricated records), pharmacy
registration/verification with immutable history, inventory with honest stock
states, versioned provenance-tracked prices with admin verification and
expiration, savings engine that refuses to invent numbers, order state machine
with price snapshots, prescription gating, AI medicine intents with safe
trilingual guidance, admin dashboard pages, Flutter screens + te/en/hi strings
(NOT COMPILED — no SDK). Verified: 142 tests, ruff clean, admin build clean,
PostgreSQL migration + integrity checks, 28/28 live HTTP smoke checks.

### Phase 5 — Digital Health Vault (COMPLETE, 2026-09-20)

Patient-controlled health records: encrypted storage abstraction with
magic-byte/size/checksum validation, consent-scoped shares (VIEW/DOWNLOAD,
expiry, revocation), short-lived signed URLs, per-record audit trail,
RBAC where no role has default clinical access, IDOR-resistant 404s,
admin governance page with aggregate metrics only, AI RECORD_SUMMARY intent
with consent-gated honesty (no fabrication, no auto-processing), Flutter
vault screens + te/en/hi strings (NOT COMPILED — no SDK). Verified:
164 tests, ruff clean, admin build clean, PostgreSQL migration (43 tables,
57 FKs, 148 indexes), 38/38 live HTTP smoke checks.

### Phase 6 — Family Accounts & Caregiver Access (COMPLETE, 2026-09-20)

A family relationship grants ZERO access: invitations (hashed one-time
tokens, 24 h, single use), relationship lifecycle (accept/decline/revoke,
partial unique index on ACTIVE pairs), owner-granted scoped consent
(six-scope allow-list, category filter, expiry, single active consent),
Health Vault integration as a third strictly-scoped authorize_access branch
(view-only, audited denials), appointment booking on behalf of the owner
(`patient_user_id` stays the owner, `requested_by_user_id` = family actor),
consent-scoped medicine-order list view (order detail + prescriptions stay
owner-only), AI FAMILY_RECORD_SUMMARY intent that explains consent instead
of retrieving, admin family governance aggregates (no names, no content),
Flutter My Family / Family Access screens + te/en/hi strings (NOT COMPILED —
no SDK). Relationship types are user-declared and never verified; legal
guardianship is explicitly out of scope. Verified: 192 tests, ruff clean,
admin build clean, PostgreSQL migration `3f8a91c4d7e2` (45 tables, 62 FKs,
156 indexes), 58/58 live HTTP smoke checks, 18/18 database integrity checks.

### Phase 7 — Emergency & SOS (COMPLETE, 2026-09-20)

Deterministic (AI-free) one-tap SOS with a service-enforced state machine
(REQUESTED → ALERTING → CONTACTING → ACTIVE → HANDOFF_PENDING → HANDED_OFF
→ RESOLVED; CANCELLED/FALSE_ALARM/FAILED terminals), race-safe idempotency
and one-active-SOS database constraints, honest cancel/false-alarm/resolve,
extended emergency contacts, patient-managed emergency profile with
minimum-necessary medical summary (missing = UNKNOWN; family access only
via ACTIVE relationship + explicit EMERGENCY_* consents), location as an
optional consent-gated snapshot, nearby VERIFIED emergency hospitals with
NOT_VERIFIED availability, ambulance provider abstraction that reports
NOT_CONFIGURED instead of faking dispatch, hospital handoff requiring real
HOSPITAL_ADMIN confirmation, honest notification ledger, emergency audit
trail, AI emergency routing (OPEN SOS + CALL 108, no treatment claims),
admin emergency governance page, Flutter emergency screens + te/en/hi
strings (NOT COMPILED — no SDK). SMS/voice/maps/ambulance/push/hospital
integrations remain explicit adapter boundaries. Verified: 227 tests,
ruff clean, admin build clean, PostgreSQL migration `c7d2e9a41b83`
(49 tables, 73 FKs, 171 indexes), 70/70 live HTTP smoke checks, 24/24
database integrity checks.
