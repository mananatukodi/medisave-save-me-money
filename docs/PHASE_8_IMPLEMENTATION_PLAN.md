# Phase 8 Implementation Plan — Partner Ecosystem

## Safety & honesty principles (non-negotiable, inherited from Phases 1–7)

- No fabricated partners, hospitals, doctors, pharmacies, labs, insurers, prices,
  claims, settlements, or emergency data. Empty catalogs are honest.
- No automated government/KYC verification claims — verification is a human
  SUPER_ADMIN decision recorded with an immutable history row, exactly like the
  Phase 3/4 provider flows.
- No fake payment settlement. Settlement rows are explicit records of what an
  operator recorded, never computed fiction; gateway integration is a
  configurable adapter boundary reported as NOT_CONFIGURED.
- No automatic claim approval. Insurance claim states change only through
  explicit, audited transitions (partner or admin), with real human decisions.
- No external delivery claims (SMS/email/push) without a configured provider —
  the same honesty ledger rules as Phase 7 notifications.
- Partner API credentials are stored ONLY as SHA-256 hashes with a prefix for
  lookup; raw keys are shown exactly once at creation (same pattern as Phase 6
  invitation tokens).

## Current architecture findings (STEP 1 inspection results)

### What already exists and MUST be reused (never recreated)

| Domain | Existing implementation | Phase |
|---|---|---|
| Identity | `users` (uuid36, email unique, bcrypt, primary_language te/en/hi), JWT access+refresh, `get_current_user` | 1 |
| RBAC | `roles`/`permissions`/`user_roles`; `require_roles(*roles)` server-side dependency; roles seeded: PATIENT, FAMILY_MEMBER, DOCTOR, HOSPITAL_ADMIN, PHARMACY_ADMIN, LAB_ADMIN, INSURANCE_PARTNER, SUPPORT_AGENT, FIELD_AGENT, SUPER_ADMIN | 1 |
| Audit | append-only `audit_logs` via `record_audit(...)` (actor/action/resource/outcome/detail) | 1 |
| Feature flags | `feature_flags` table; per-route gate pattern `_flag_enabled(db, key)`; PATCH is SUPER_ADMIN-only | 1 |
| Consents | `consents` with CONSENT_TYPES enum incl. INSURANCE_ACCESS, HOSPITAL_ACCESS, DOCTOR_ACCESS | 1 |
| Specialties | 17 seeded specialties (trilingual) + `specialty_services` (eye/dental catalogs) | 1 |
| Doctors | `doctors` (+ `user_id` link), `doctor_verifications` immutable history, PENDING→VERIFIED admin workflow, `provider_services`, `service_prices` (UNVERIFIED/VERIFIED + provenance), `service_availability`, `provider_blocks`, `provider_specialty_links` | 3 |
| Hospitals | `hospitals` (+ `admin_user_id`), `hospital_verifications`, emergency_available/emergency_verified flags | 3 |
| Appointments | `appointments` state machine (REQUESTED→CONFIRMED→…) with partial unique index `uq_active_appointment_slot`; ownership = patient or owning doctor (`doctor.user_id`) | 3 |
| Medicines/Pharmacy | `medicines`, `medicine_aliases`, `pharmacies` (+ `admin_user_id`), `pharmacy_verifications`, `pharmacy_inventory`, `medicine_prices` (versioned, is_current, verification lifecycle), `medicine_price_history`, `medicine_orders` (immutable snapshots), `medicine_order_items`, `prescription_requests` (human Rx review gate) | 4 |
| Health Vault | `stored_files` (encrypted at rest, opaque object keys, checksums, Fernet/AES+HMAC metadata), `health_records`, `health_record_shares`, `health_record_access_events`; signed download URLs | 5 |
| Family access | `family_relationships` + `family_access_consents` (scopes re-checked per request; SHA-256 invitation tokens shown once) | 6 |
| Emergency | `emergency_events` (Phase 7 state machine, idempotency partial indexes), `emergency_handoffs` (hospital-side real confirmation), `emergency_notifications` (honest delivery ledger), `emergency_provider_events` (ambulance adapter ledger), `AmbulanceProvider` protocol (NOT_CONFIGURED default) | 7 |
| Storage | `app/services/storage.py` — `StorageProvider` protocol, `LocalEncryptedStorage`, S3 skeleton, MIME magic-byte validation, `sanitize_filename`, checksums | 5 |
| Rate limiting | `SlidingWindowLimiter` per route group (`rate_limit_auth/ai/search`) | 3 |
| Admin UI | React pages per domain, aggregate-only governance pages (Vault/Family/Emergency), axios client in `admin/src/api.ts` | 1–7 |
| Flutter | riverpod + dio + go_router + 3-locale ARBs; patient-facing screens per feature dir | 1–7 |
| Migrations | Alembic head `c7d2e9a41b83` (Phase 7), 49 tables / 73 FKs / 171 indexes on PostgreSQL 16 | 7 |

### Duplicate models that must NOT be recreated

- **Doctors / hospitals / pharmacies / appointments / orders**: partner
  integration must *link* to the existing `doctors`, `hospitals`, `pharmacies`,
  `appointments`, `medicine_orders` rows — never create parallel partner copies.
- **Verification histories**: the per-provider verification tables remain the
  source of truth for provider-specific verification; the partner layer adds an
  *organization-level* verification lifecycle without touching those tables.
- **Documents**: `stored_files` remains the only storage engine; partner
  documents reference it via `file_id` instead of introducing new storage.
- **Notifications**: the Phase 7 honest-ledger pattern is generalized into a
  partner notification table with the same QUEUED/SENT/DELIVERED/FAILED and
  `provider_not_configured` semantics — not a new delivery system.
- **Claims/settlements/commissions**: none exist anywhere in the codebase today
  (verified by search) — these are genuinely new, built once, generically.

### Missing partner architecture (to be added)

1. **Organizations** — no org model exists anywhere; every current provider is
   single-admin (`admin_user_id` / `user_id` columns).
2. **Organization membership** — no way for multiple users to belong to one
   partner organization with partner-scoped roles.
3. **Organization-scoped RBAC** — `require_roles` is role-only; every partner
   query must additionally be scoped by `organization_id` membership.
4. **Partner lifecycle** — the 8-state partner workflow (DRAFT…DEACTIVATED).
5. **Partner documents/KYC** — upload/verify/reject/expire with real storage.
6. **Partner services catalog** — generic service rows per organization.
7. **Claims** — no claim model exists at all.
8. **Settlements/commissions** — architecture only; no fake amounts.
9. **Webhooks/API credentials** — hashed keys, HMAC-signed deliveries,
   idempotent event ledger.
10. **Partner notifications** — channel ledger with honest statuses.
11. **Lab & insurance partner modules** — no lab test catalog or insurance
    policy/claim models exist; both are created here, generically, never
    seeded with fabricated tests/prices/coverage.

## Reuse map (no parallel systems)

| Need | Reuses |
|---|---|
| Partner identity | `users` + JWT `CurrentUser` |
| Partner roles | `require_roles` + new PARTNER_* role ids seeded additively |
| Org scoping | new `require_partner_org(...)` dependency + `OrganizationMember` |
| Partner profile data | new `partner_profiles` JSON metadata keyed by organization_type |
| KYC documents | `stored_files` (encrypted) + new `partner_documents` |
| Doctor/hospital/pharmacy links | `doctors.hospital_id`, `doctors.user_id`, `pharmacies.admin_user_id`, `provider_specialty_links` — linked via `partner_profiles` FK columns |
| Lab profile | `partner_profiles` (organization_type=LAB) + `partner_lab_tests` catalog |
| Insurance profile | `partner_profiles` (organization_type=INSURANCE) + `partner_insurance_products` |
| Emergency provider | `EmergencyProviderEvent` ledger + `AmbulanceProvider` adapter (unchanged) |
| Audit | `record_audit` + new PARTNER_* action names |
| Flags | `feature_flags` (11 new keys, OFF by default) |
| Admin governance | existing admin router + React governance-page pattern |

## Partner data model (one additive migration `a1b2c3d4e5f6_phase_8_partner_ecosystem`)

New tables (11; nothing existing is altered):

1. `organizations` — organization_type (DOCTOR/HOSPITAL/PHARMACY/DIAGNOSTIC_LAB/
   INSURANCE/AMBULANCE), legal_name, display_name, registration_number (empty
   allowed), tax_identifier (nullable), contact fields, geo, status
   (ACTIVE/INACTIVE), verification_status mirror, timestamps. Unique display
   name per type is NOT enforced (display names may repeat in reality);
   `registration_number` uniqueness is scoped per (type, registration_number)
   via a partial index only when non-empty — no invented values.
2. `organization_members` — (organization_id, user_id) with partner role
   PARTNER_OWNER/PARTNER_ADMIN/PARTNER_MANAGER/PARTNER_STAFF/PARTNER_BILLING/
   PARTNER_SUPPORT; one ACTIVE membership per (org, user) partial unique index;
   `is_active` + `revoked_at` for stale-membership revocation.
3. `partner_profiles` — one per organization (unique), type-specific metadata:
   JSON `metadata` column + explicit link columns `doctor_id`, `hospital_id`,
   `pharmacy_id` (FKs to existing tables, nullable). Lab/insurance/ambulance
   specifics live in typed metadata + their own tables below.
4. `partner_documents` — organization_id, document_type (BUSINESS_REGISTRATION,
   PROFESSIONAL_LICENSE, PHARMACY_LICENSE, LAB_LICENSE, INSURANCE_LICENSE,
   HOSPITAL_REGISTRATION, TAX_DOCUMENT, IDENTITY_DOCUMENT, ADDRESS_PROOF,
   OTHER), `file_id` FK → stored_files, checksum, issued_at/expires_at,
   verification_status (UPLOADED/UNDER_REVIEW/VERIFIED/REJECTED/EXPIRED),
   verified_by/verified_at, review notes. Never public.
5. `partner_services` — organization_id, service_type, name, description,
   status (ACTIVE/INACTIVE), price (nullable) + currency, verification_status
   (UNVERIFIED/VERIFIED — provider-declared prices are never shown as verified),
   source, timestamps. No fabricated pricing: price nullable.
6. `partner_lifecycle_events` — append-only history of every status transition
   (previous_status, new_status, actor, note) — mirrors the Phase 3/4
   verification-history pattern.
7. `partner_claims` — organization_id, patient_user_id, claim_number (unique
   when present), subject_type (APPOINTMENT/ORDER/LAB_BOOKING/OTHER),
   subject_id, status per the 9-state claim machine, amount/currency
   (nullable — never invented), submitted_by, decided_by/timestamps.
8. `partner_claim_events` — append-only claim transition history.
9. `partner_lab_tests` — organization_id, code, name, description, category,
   sample_type, preparation_notes, price nullable + currency,
   verification_status, is_active. Catalog is partner-entered; admin-verified
   before public display; nothing seeded.
10. `partner_insurance_products` — organization_id, product_name, product_type,
    coverage summary text (partner-declared, never treated as verified truth),
    status, timestamps. Plus `partner_insurance_policies` — patient-held policy
    references (policy_number, product FK, patient, metadata) recorded from
    real submissions only.
11. `partner_integrations` — organization_id, integration_kind
    (WEBHOOK_ENDPOINT/API_KEY), name, endpoint_url (webhooks), `key_prefix` +
    `key_hash` (SHA-256; never plaintext), scopes CSV, status, last_used_at,
    secret_version. Plus `partner_webhook_events` — append-only event ledger
    (event_id UUID unique, event_type, organization_id, payload JSON,
    delivery_status PENDING/DELIVERED/FAILED, attempts, last_response_code,
    idempotency support). Plus `partner_settlements` — explicit operator/finance
    recorded rows (period_start/end, gross_amount, platform_fee, net_amount,
    currency, status, external_reference, recorded_by) — no gateway calls, no
    computed fiction; amounts nullable until a real finance action supplies
    them. Plus `partner_commissions` — configuration rows (commission_type
    PERCENT/FIXED, commission_value, currency, effective_from/until,
    service_type, status) for future commercial rules; never applied
    automatically in this phase. Plus `partner_notifications` — channel ledger
    (IN_APP/PUSH/SMS/EMAIL × QUEUED/SENT/DELIVERED/FAILED, provider_name,
    error_detail) with the same honesty contract as Phase 7.

Indexes: FK indexes on every organization_id column; partial unique
`uq_org_member_active` on (organization_id, user_id) where is_active; unique
`uq_partner_webhook_event_id`; partial unique on (org, code) for lab tests
where active; partial unique on claim_number where non-empty.

## Partner lifecycle (service-enforced state machine)

```
DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED
UNDER_REVIEW -> VERIFICATION_REQUIRED -> UNDER_REVIEW | REJECTED
SUBMITTED -> UNDER_REVIEW | REJECTED
VERIFICATION_REQUIRED -> UNDER_REVIEW
APPROVED -> SUSPENDED | DEACTIVATED
SUSPENDED -> APPROVED | DEACTIVATED
REJECTED -> UNDER_REVIEW (re-submission review)
DEACTIVATED -> (terminal)
```

Non-APPROVED organizations cannot: create services, upload documents (except
while DRAFT/SUBMITTED), manage members beyond owner, or appear in patient-facing
partner discovery. SUSPENDED/REJECTED/DEACTIVATED cannot perform any
patient-facing operation. Every transition is written to
`partner_lifecycle_events` AND `audit_logs`.

## Organization-scoped RBAC (the core security primitive)

- New dependency `require_partner_org(organization_id_path_param)`:
  1. resolves the caller's ACTIVE `OrganizationMember` row for the org in the
     path (or the `X-Organization-Id` scoped dashboard route),
  2. 404 (existence-hidden) when no membership — never 403 (no existence leak),
  3. 403 when membership is inactive/revoked (explicit, audited),
  4. 403 when the organization is not APPROVED for protected operations,
  5. enforces role minimums per endpoint (e.g. only PARTNER_OWNER/PARTNER_ADMIN
     manage members; PARTNER_BILLING sees claims).
- SUPER_ADMIN bypasses org membership for admin governance endpoints only
  (audited), never for patient-owned data.
- The client-supplied `organization_id` in a body is never trusted; scope is
  derived from the path parameter + membership.

## API surface (follows existing conventions: /api/v1, 401/403/404/409/422/503)

Partner self-service (organization-scoped):
- `POST /partners` (onboard; creates DRAFT org + owner membership + profile)
- `GET /partners/mine` (organizations of the caller)
- `GET/PATCH /partners/{org_id}`
- `POST /partners/{org_id}/submit` · `/review` (admin) · `/approve` ·
  `/reject` · `/suspend` · `/reactivate` · `/deactivate`
- `POST/GET /partners/{org_id}/documents`; `POST /partners/{org_id}/documents/{doc_id}/decision`
- `POST/GET /partners/{org_id}/members`; `PATCH/DELETE /partners/{org_id}/members/{member_id}`
- `GET/POST/PATCH /partners/{org_id}/services`
- `GET /partner/dashboard` (aggregated ops view for all my orgs)

Admin (SUPER_ADMIN):
- `GET /admin/partners` (+status/type filters), `GET /admin/partners/{id}`
- approve/reject/suspend/reactivate/deactivate + document decision + overview
  (aggregate counts: orgs by type/status, pending docs, claims/appointments/
  orders aggregates — no patient content)

Partner-type operational endpoints:
- Lab: `POST/GET /partners/{org_id}/lab/tests`, PATCH test, `GET /lab-tests`
  (verified, public), `POST /partners/{org_id}/lab/bookings`, state transitions,
  report delivery via existing vault share rules
- Insurance: `POST/GET /partners/{org_id}/insurance/products`,
  `POST /partners/{org_id}/insurance/claims`, claim transitions
  (partner + admin), `GET /insurance/claims` (patient's own claims)
- Webhooks/keys: `POST/GET /partners/{org_id}/integrations`
  (API keys hashed; webhook endpoint registration); events recorded on
  appointment/order/claim changes (delivery is adapter-based and honest)

## Feature flags (all OFF by default)

`partner_ecosystem`, `partner_onboarding`, `partner_verification`,
`partner_services`, `partner_claims`, `partner_settlement`,
`partner_webhooks`, `partner_api`, `partner_lab`, `partner_insurance`,
`partner_emergency` — seeded idempotently; partner routes 503 when their flag
is off (same pattern as SOS/AI).

## Integration with existing phases (link, never duplicate)

- DOCTOR orgs link `partner_profiles.doctor_id → doctors.id`; appointment
  visibility for partner staff resolves through this link — appointment state
  machine and partial unique index untouched.
- HOSPITAL orgs link `partner_profiles.hospital_id → hospitals.id`; emergency
  handoff decisions continue to use `hospital_decide_handoff` (extended to
  accept organization-linked hospital admins without changing its contract).
- PHARMACY orgs link `partner_profiles.pharmacy_id → pharmacies.id`; orders
  remain gated by verified prices/prescription review — partner staff access
  orders through the org link with minimum-necessary patient fields.
- LAB bookings reference `partner_lab_tests` + `partner_lab_bookings`; reports
  are delivered as Health Vault records respecting Phase 5 authorization.
- INSURANCE claims reference existing subjects (appointment/order ids) and
  never auto-approve; INSURANCE_ACCESS consent remains the patient gate for
  data shared with insurers.
- Emergency: AMBULANCE orgs register through the partner flow; dispatch stays
  behind the `AmbulanceProvider` adapter (NOT_CONFIGURED until integrated).

## Test plan (new `tests/test_partners.py` + `tests/test_partner_modules.py`)

Registration/onboarding, lifecycle transitions (valid + invalid + terminal),
document upload/verify/reject/expire, membership add/update/remove, RBAC
matrix (staff vs admin vs billing), **organization isolation/BOLA** (org A
staff cannot read/write org B organizations, documents, services, members,
claims, lab bookings — existence-hidden 404s; body-supplied organization_id is
ignored), suspended/rejected partners blocked, service management + price
honesty (declared ≠ verified), doctor/hospital/pharmacy links, lab catalog +
booking lifecycle, insurance products + claim machine (no auto-approval),
API key hashing (raw shown once, hash-only storage, auth via hashed compare),
webhook event ledger + idempotent event ids, claims/settlement no-fabrication,
audit rows for every sensitive action, flag-gating 503s.

## Verification gates (STEP 11–12)

Full pytest (Phase 1–7 suites must stay green), `ruff check app tests`,
`alembic upgrade head` on SQLite + PostgreSQL when available, DB integrity
script (tables/FKs/orphans), HTTP smoke, `tsc -b && vite build` for admin,
Flutter compile ONLY if the SDK exists (otherwise honestly documented as
NOT COMPILED — REQUIRES FLUTTER SDK).

## Production integration blockers (documented, not faked)

Government/KYC registry verification, payment gateway settlement, SMS/email/
push providers, webhook outbound delivery workers, real ambulance dispatch,
insurance TPA integration, lab LIS integration — all remain honest
NOT_CONFIGURED boundaries.
