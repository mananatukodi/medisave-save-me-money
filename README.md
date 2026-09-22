# MediSave AI — Save Me Money

> "Your Health, Our Priority. Your Money, Our Savings."
> **Smart Healthcare. Better Care. Lower Cost.**

MediSave AI is a **patient-first digital healthcare ecosystem**: one secure health profile for the
complete healthcare journey — discovery, specialty care (Eye Care, Dental Care, …), AI-assisted
health navigation, medicine savings, health records, insurance, and emergency SOS.

⚠️ **Honesty policy (non-negotiable):** this repository contains **no fabricated healthcare data** —
no fake doctors, hospitals, medicines, prices, insurance coverage, or dispatch confirmations.
Anything not backed by a real, verified integration is labeled `DEMO` / `SAMPLE` / `NOT REAL`
or reported as `NOT IMPLEMENTED` / `REQUIRES INTEGRATION`.

## Repository layout

| Path | Stack | Status |
|------|-------|--------|
| `backend/` | Python 3.13 + FastAPI + SQLAlchemy 2.0 + Alembic (PostgreSQL verified) | ✅ implemented, 87 tests passing (Phases 1-3) |
| `admin/` | React 18 + TypeScript + Vite admin dashboard | ✅ builds clean (Phases 1 + 3) |
| `mobile/` | Flutter patient app (Riverpod, GoRouter, Dio, l10n te/en/hi) | ✅ authored — build `REQUIRES FLUTTER SDK` |
| `docs/` | Architecture, API, DB, security, AI safety, deployment docs | ✅ |
| `docs/MEDISAVE_AI_IMPLEMENTATION_PLAN.md` | Canonical inspection report + phased plan | ✅ |

## Quickstart — backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows (bash: source .venv/Scripts/activate)
pip install -e ".[dev]"
copy .env.example .env                              # then edit values
# Local dev without Postgres: keep MEDISAVE_DATABASE_URL=sqlite:///./medisave.db
# With Postgres: create the DB, then run migrations:
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# Health: http://localhost:8000/health  ·  OpenAPI: http://localhost:8000/docs
```

## Quickstart — admin dashboard

```bash
cd admin
npm install
npm run dev      # http://localhost:5173 (expects backend on :8000)
npm run build    # typecheck + production build
```

## Quickstart — mobile (requires Flutter SDK — not installed on this machine)

```bash
cd mobile
flutter pub get
flutter run
```

## Current implementation status (spec §49 phases)

- ✅ **Phase 1 — Foundation:** JWT auth (access+refresh), server-side RBAC (10 roles), consents,
  audit log, feature flags, specialties catalog (17 specialties incl. Eye Care & Dental Care),
  health checks, rate limiting, Alembic migration, pytest suite.
- ✅ **Phase 2 — AI Health Assistant:** sessions, messages, 28-intent rule-based classifier,
  emergency screening (EN/TE/HI keywords), red-flag detection, safety-validated structured
  responses, consent gate, audit events, AI provider abstraction (LLM = `REQUIRES INTEGRATION`).
- ✅ **Phase 3 — Healthcare Access:** doctor/hospital registration + 5-state verification workflow
  (audited, immutable history), multi-specialty links, provider services with provenance-tracked
  prices, availability engine (rules/blocks/slots), appointment state machine with server-side
  double-booking prevention (partial unique index proven on PostgreSQL 16), rate limiting on
  auth+AI, docker-compose stack, admin verification queue, Flutter discovery/booking screens
  (authored — build `REQUIRES FLUTTER SDK`).
- 🔜 Phase 4+ (medicines/savings, health vault, insurance, SOS dispatch, partner portals, scale):
  see the implementation plan for the honest per-module status.

## Documentation

Start with `docs/MEDISAVE_AI_IMPLEMENTATION_PLAN.md`, then `docs/ARCHITECTURE.md`,
`docs/AI_SAFETY.md`, `docs/SECURITY.md`, `docs/DATABASE.md`, `docs/API.md`,
`docs/LOCALIZATION.md`, `docs/OFFLINE_MODE.md`, `docs/DEPLOYMENT.md`, `docs/TESTING.md`.
