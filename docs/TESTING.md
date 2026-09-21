# MediSave AI — Testing

Run: `cd backend && .venv/Scripts/python -m pytest` → **269 passed** (current, on Python 3.13; Phases 1–7 + Phase 8 partner ecosystem).

## Backend suites (pytest)

| File | Covers |
|------|--------|
| `tests/test_health.py` | `/health`, `/ready`, `/version` (spec §40) |
| `tests/test_auth_rbac.py` | register/login/refresh, token-type confusion, self-role-escalation blocked, 401/403 RBAC matrix, flag updates SUPER_ADMIN-only |
| `tests/test_consents.py` | grant/revoke, enum validation, double-revoke 409, cross-user 404 (spec §30) |
| `tests/test_specialties.py` | 17 specialties, trilingual names, Eye/Dental service catalogs (spec §6) |
| `tests/test_ai_safety.py` | emergency screening (EN/TE/HI), consent bypass for emergencies, disclaimer in 3 languages, no-certainty/no-fabricated-prices, response shape (spec §11) |
| `tests/test_ai_api.py` | flag gate 503, consent gate 403, session continuity + cross-user 404, Telugu chat, emergency flow |
| `tests/test_emergency.py` | SOS starts REQUESTED (never CONFIRMED), cancel rules, contacts CRUD (spec §12) |
| `tests/test_admin.py` | audit-log visibility, LOGIN/ROLE_CHANGE audited, role assignment (spec §32/§37) |
| `tests/test_providers.py` | doctor/hospital registration (role-gated, PENDING start), verification flow incl. suspension + immutable history, unknown specialty rejection, public-view privacy, search filters, audit of decisions (spec §1-§4, §14) |
| `tests/test_booking.py` | availability slot computation, provider-declared prices stay UNVERIFIED, booking unverified doctor rejected, happy-path booking, double-booking 409, blocks, state machine transitions, patient-vs-provider RBAC, ownership 404s, cancel/reschedule freeing slots, scoped listings, audit (spec §8-§10) |
| `tests/test_family.py` | Phase 6 invitation security (token shown once / never re-exposed, expiry 410, stranger acceptance 403, self-invite 422, duplicate ACTIVE 409), relationship lifecycle (decline, member self-remove, stranger 404), consent (requires ACTIVE relationship, unknown scope 422, member cannot self-grant, replace + revoke), vault integration (consented view, no default access 403, category filter, revoked/expired consent 403, download blocked, owner retention), appointments on behalf (patient stays owner, requester = member, no-consent 403, stranger 403), medicine-order scope + denial, access history audit |
| `tests/test_emergency_phase7.py` | Phase 7 emergency: state machine (valid/invalid/terminal), idempotency (same-key same-event) + active-dedup (retries never rejected), cancel/false-alarm/resolve rules, location snapshot, RBAC/IDOR (stranger 404 on view/cancel/resolve/audit/summary), contacts priority/active + ownership, profile upsert + ownership, medical-summary UNKNOWN honesty + family consent gating (grant/revoke/expiry), family alerts (RECEIVE_HEALTH_ALERTS, location only with EMERGENCY_LOCATION consent, strangers excluded), nearby hospitals (auth, VERIFIED+emergency filter, NOT_VERIFIED honesty), handoff lifecycle with real hospital-admin decision + cross-hospital 403, ambulance NOT_CONFIGURED honesty + ledger, notification honesty, audit trail, AI routes-to-SOS without treatment claims |

Test infra: in-memory SQLite via `StaticPool` + dependency override; `seed()` runs per test session fixture.

## Phase 8 verification (2026-09-21)

- Backend: **269 passed** — 227 Phases 1–7 (unchanged) + **42 partner tests**
  (`tests/test_partners.py` + `tests/test_partner_modules.py`).
- Partner tests cover: registration + DRAFT/owner membership, flag gating 503s,
  lifecycle (submit→review→approve; invalid transitions 409; suspended blocked
  from operations; DEACTIVATED terminal), **organization isolation/BOLA**
  (A→B reads/members/documents/services/submit/member-add all 404;
  body-supplied organization_id never trusted; stale membership 403),
  membership RBAC (staff cannot manage members or decide claims; owner role
  immutable/irremovable; duplicate active membership 409), documents (invalid
  type 422; partner cannot self-verify; re-decision 409), services (declared
  price stays UNVERIFIED; DRAFT org 403; price change resets verification),
  API keys (raw shown once, hash-only storage, roundtrip + tamper rejection),
  webhook honesty (https-only; events PENDING without delivery worker; unknown
  event types ignored), notifications (IN_APP real + org-scoped), audit rows,
  admin overview, lab catalog honesty (UNVERIFIED hidden from public; VERIFIED
  + APPROVED org required; suspend hides), lab booking state machine, insurance
  products, claim machine (no auto-approval; staff cannot approve; terminal
  SETTLED), claim isolation across orgs, patient-owner-scoped claims, and
  settlement/commission no-fabrication (amounts stay None; no apply logic).
- Live HTTP smoke: **76/76** against PostgreSQL (`scripts/phase8_smoke_test.py`)
  — flag gating, onboarding, isolation, verification lifecycle, document + lab
  test verification, public-catalog honesty before/after verification, lab
  booking, insurance claim flow with human approval, API key hash-only
  exposure, webhook https enforcement, partner dashboard/notifications, admin
  governance, plus Phase 1–7 live probes (specialties/doctors/pharmacies/
  medicines/orders/vault/emergency/family scope). Smoke data cleaned up
  afterwards; partner flags restored to OFF.
- Database: Alembic head `b4f8d2a6c9e1` applied on PostgreSQL 16 — 67 tables,
  18 new partner tables, 0 FK orphans, 6 partial unique indexes present,
  Phase 1–7 data intact (75 users, 14 orders, 15 emergency events, 10 vault
  records preserved). Migration verified additively on SQLite as well.
- Ruff: clean (`app tests scripts`). Admin: `tsc -b` + `vite build` clean
  (250.92 kB, gzip 80.79 kB).
- Flutter: **NOT COMPILED — Flutter SDK unavailable on this machine.** Phase 8
  keeps partner administration web-based by design; the patient app's partner
  surfaces (find verified partner, partner services, booking, orders, claims)
  continue through the existing Phase 3–7 screens + the public `/lab-tests`
  and `/insurance/claims` endpoints.
- Known pre-existing limitation (documented, not introduced by Phase 8): the
  Phase 7 migration uses plain `ALTER` on `emergency_events`, which Alembic
  cannot replay from scratch on SQLite (`batch_alter_table` is the Phase 6
  convention). On PostgreSQL (the production target) it applies cleanly; fresh
  SQLite deployments create the schema via `Base.metadata.create_all`.

## Live verification (Phase 3)

- `scripts/smoke_test.py` — 14/14 checks against a live server on **real PostgreSQL 16** (docker compose), covering the full Phase 1-3 surface including doctor/hospital/appointment endpoints and verification-queue RBAC.
- `scripts/pg_check.py` — proves the partial unique index blocks double booking **in Postgres itself** (second CONFIRMED insert raises IntegrityError; CANCELLED row on the same slot is allowed).

## Not yet automated (honest gaps)

- Admin UI tests (no harness yet) — manual verification only.
- Flutter widget/localization tests — `REQUIRES FLUTTER SDK`.
- Payment-state machine tests — payments land in a later phase.
- Load/security scanning (`pip-audit`, `npm audit`) — wired next into CI.

## Phase 6 verification (2026-09-20)

- Backend: **192 passed** — 164 Phase 1–5 + 27 family + 1 AI family-intent test.
- Family tests cover the full security matrix: invitation reuse/guessing/expiry,
  relationship-without-consent, wrong scope/category, revoked + expired consent,
  owner self-access, stranger 404 (no IDOR), AI never bypasses consent.
- Live HTTP smoke: **58/58** against PostgreSQL — family invite → accept →
  scoped vault access → category denial → consent revoke → expiry → on-behalf
  appointment (`patient_user_id` = owner, `requested_by_user_id` = member) →
  medicine-order scope → order-detail/prescription owner-only → AI family
  intent → relationship revoke → re-invite → single-use reuse 409 → audit →
  FK-safe fixture cleanup.
- Database: `scripts/phase6_db_check.py` **18/18** (45 tables / 62 FKs /
  156 indexes, partial unique index present, zero orphans, no leftover
  synthetic fixtures, Phase 1–5 data intact).
- Ruff clean (`app tests scripts`; CI scope `app tests`). Alembic head
  `3f8a91c4d7e2`.
- Admin: `tsc -b` + `vite build` clean (Family Governance page added).
- Flutter: family screens + te/en/hi keys complete as source; NOT compiled
  (Flutter SDK unavailable).

## Phase 7 verification (2026-09-20)

- Backend: **227 passed** — 192 Phases 1–6 + 35 emergency tests
  (6 pre-existing Phase 1 SOS/contacts contracts unchanged and passing).
- Live HTTP smoke: **70/70** against PostgreSQL — adds 12 emergency checks:
  AI-independent SOS creation, idempotency same-key/same-event, active-dedup,
  emergency profile + UNKNOWN honesty, family minimal alerts (location gated
  by EMERGENCY_LOCATION consent), nearby hospitals NOT_VERIFIED, ambulance
  NOT_CONFIGURED + ledger, IN_APP notification SENT, FALSE_ALARM terminal,
  new-SOS-after-terminal, audit trail.
- Database: `scripts/phase7_db_check.py` **24/24** (49 tables / 73 FKs /
  171 indexes, partial unique indexes present, orphan-free FK graph,
  no fabricated DELIVERED/DISPATCHED states, Phase 1–6 data intact).
- Ruff clean; Alembic head `c7d2e9a41b83`; admin `tsc -b` + `vite build` clean.
- Flutter: 7 emergency screens + routes + te/en/hi keys (174 per locale,
  aligned); NOT compiled (Flutter SDK unavailable).

## Phase 5 verification (2026-09-20)

- Backend: **164 passed** (`pytest -p no:warnings`) — 142 Phase 1–4 + 21 vault + 1 AI vault-intent test.
- Vault tests cover: ownership, stranger 404 (no IDOR), role denial (support agent / hospital admin),
  share create/view/revoke, post-revocation 403, expired share 403, wrong-scope 403, upload validation
  (bad type, oversized, magic bytes), checksum + duplicate detection, signed-URL issuance + expiry,
  object-key privacy, audit trail, soft-delete + file purge.
- Live HTTP smoke: **38/38** against PostgreSQL — includes the full consent lifecycle
  (share → doctor view → revoke → 403; expired share → 403; stranger → 404; audit events recorded;
  metadata exposes no object keys/paths).

## Phase 4 verification (2026-09-19)

- Backend: **142 passed** (`pytest -p no:warnings`) — 87 existing + 25 pharmacy/pricing/savings + 17 orders + 13 AI medicine intents.
- Ruff: clean. Admin: `tsc -b && vite build` clean.
- PostgreSQL (Docker): migration `2a34b8868e53` applied; 39 tables; 47 FKs; 124 indexes; `scripts/pg_check.py` all PASS (inventory uniqueness, price versioning, order snapshot independence).
- Live HTTP smoke: **28/28** against PostgreSQL — includes honesty proofs (unverified pharmacy excluded; `INSUFFICIENT_DATA` instead of fabricated savings; Rx order pauses at `PRESCRIPTION_REQUIRED`).
