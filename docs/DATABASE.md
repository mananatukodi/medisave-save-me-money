# MediSave AI — Database

PostgreSQL (runtime `REQUIRES POSTGRES` — not installed on the build machine; the test suite runs on in-memory SQLite with identical schemas).

## Migrations

```bash
cd backend
alembic upgrade head          # apply
alembic revision --autogenerate -m "..."   # after model changes
```

Applied initial migration: `alembic/versions/c916d59c142b_initial_core_tables.py` (19 tables, verified against a scratch DB).

## Tables (current)

| Group | Tables |
|-------|--------|
| Identity & RBAC | `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `family_members` |
| Consent | `consents` (type, purpose, dataScope, recipient, duration, grantedAt, revokedAt, expiresAt) |
| AI | `ai_sessions`, `ai_messages`, `ai_events` |
| Specialty care | `specialties`, `specialty_services`, `provider_specialties`, `provider_specialty_links` (multi-specialty) |
| Providers (Phase 3) | `doctors`, `doctor_verifications`, `hospitals`, `hospital_verifications` (immutable decision history) |
| Provider services (Phase 3) | `provider_services`, `service_prices` (source/last_updated/verification_status), `service_availability`, `provider_blocks` |
| Appointments (Phase 3) | `appointments` — partial unique index `uq_active_appointment_slot` blocks double booking for active statuses; cancelled/completed rows excluded |
| Emergency | `emergency_events` (status REQUESTED→CONFIRMED only via real provider), `emergency_contacts` |
| Ops | `audit_logs` (append-only), `feature_flags`, `system_settings` |

## Deliberately NOT created yet (Phase 4+; awaiting real data workflows)

`pharmacies`, `labs` (+ verifications), `medicines`, `medicine_prices`,
`inventory`, `payments`, `health_records`, `prescriptions`, `lab_reports`,
`insurance_policies`, `insurance_claims`, `notifications`, `reviews`, `support_tickets`,
`referrals`, `specialty_appointments`, `specialty_packages`.

Per spec §2/§54, these ship **with** their verification/consent flows, not as empty scaffolds with
fake rows. Verified-price rows must carry `source`, `lastUpdated`, `currency`, `availability`,
`verificationStatus`.

## Migrations (current)

1. `c916d59c142b` — initial core tables (19 tables)
2. `ffff2f1bd46e` — Phase 3 providers + appointments (10 tables + partial unique index)

Both verified against real PostgreSQL 16 (docker compose) and SQLite (test suite).

## Phase 4 tables (migration `2a34b8868e53`)

`medicines`, `medicine_aliases`, `pharmacies`, `pharmacy_verifications`,
`pharmacy_inventory` (unique per pharmacy+medicine), `medicine_prices`
(versioned, `is_current` flag), `medicine_price_history` (append-only),
`medicine_orders`, `medicine_order_items` (price snapshots),
`prescription_requests`. Search paths are indexed
(`medicines.name/generic_name/brand_name/manufacturer`,
`pharmacies.city/state/postal_code`, composite status indexes).

## Phase 5 tables

`stored_files` (opaque `object_key`, `checksum_sha256`, `encryption_metadata`,
`upload_status`), `health_records` (owner `patient_id`, category, `file_id`
FK with `SET NULL`), `health_record_shares` (scope/purpose/expiry/revocation),
`health_record_access_events` (per-record audit: VIEW / DOWNLOAD_URL /
SHARE_CREATED / SHARE_REVOKED / DENIED). Deletion order is enforced by FK:
a file cannot be deleted while a record references it; deleting a record
purges its file and dependent shares/events — never unrelated patient data.

## Phase 6 tables (migration `3f8a91c4d7e2`)

`family_relationships` (owner/member FKs to `users.id`, member nullable for
email invitations, `display_name`, user-declared `relationship_type`,
`status` INVITED/ACTIVE/DECLINED/REVOKED/EXPIRED, `invitation_token_hash`
(SHA-256, never raw), `invitation_expires_at`, accept/decline/revoke
timestamps) and `family_access_consents` (FK to the relationship,
comma-separated `scopes` validated against the server allow-list,
`category_filter`, `purpose`, `granted_by` FK, `expires_at`, `revoked_at`).

Key constraint: **partial unique index `uq_family_active_relationship`** —
only one ACTIVE relationship per (owner, member) pair (`status = 'ACTIVE'`
where-clause on both SQLite and PostgreSQL dialects). Four FKs:
`fk_family_rel_owner`, `fk_family_rel_member`, `fk_family_consent_rel`,
`fk_family_consent_granter` — no orphan rows are possible in either table.
Relationship status is re-queried on every vault/order/appointment access,
so REVOKED/EXPIRED rows deny immediately.

Totals after Phase 6 (verified on PostgreSQL 16): **45 tables ·
62 foreign keys · 156 indexes**; Alembic head `3f8a91c4d7e2`.
Verification script: `backend/scripts/phase6_db_check.py` (read-only;
constraints, orphans, fixture cleanup, Phase 1–5 data preservation).

## Phase 7 tables (migration `c7d2e9a41b83`)

`emergency_events` extended additively (`emergency_type`,
`initiated_by_user_id`, `idempotency_key`, `correlation_id`,
`location_timestamp`, `network_status`, `device_platform`, `cancel_reason`,
`resolved_by_user_id`, initiated/cancelled/resolved timestamps) with two
race-safe partial unique indexes: **`uq_patient_active_sos`** (at most one
non-terminal SOS per patient) and **`uq_sos_idempotency`** (same user +
same key → same event). `emergency_contacts` gained `priority`, `active`,
`notification_preferences`, `updated_at`.

New tables: `emergency_profiles` (one per user, all fields optional),
`emergency_handoffs` (event + VERIFIED hospital + requester + status
machine), `emergency_notifications` (honest delivery ledger:
QUEUED/SENT/DELIVERED/FAILED with `error_detail`),
`emergency_provider_events` (append-only ambulance-provider ledger).

Totals after Phase 7 (verified on PostgreSQL 16): **49 tables ·
73 foreign keys · 171 indexes**; Alembic head `c7d2e9a41b83`.
Verification script: `backend/scripts/phase7_db_check.py` (read-only;
22 checks incl. orphan-free FK graph, VERIFIED-hospital handoffs, and
no fabricated DELIVERED/DISPATCHED states).

## Phase 8 tables (migration `b4f8d2a6c9e1`)

Partner ecosystem — 18 additive tables, no existing table altered:

- Core: `organizations` (6 types, lifecycle status + verification mirror),
  `organization_members` (6 partner roles; partial unique `uq_org_member_active`
  on (org, user) where active — stale memberships are revoked, not recreated),
  `partner_profiles` (type metadata JSON + FK links to existing
  `doctors`/`hospitals`/`pharmacies` — providers are linked, never duplicated).
- Governance: `partner_lifecycle_events` (append-only status history),
  `partner_documents` (FK to Phase 5 `stored_files`; checksum; issued/expires;
  human verification decision fields).
- Operations: `partner_services` (declared prices start UNVERIFIED),
  `partner_claims` (9-state machine; partial unique claim_number when present),
  `partner_claim_events` (append-only).
- Lab: `partner_lab_tests` (partial unique (org, code) where active; prices
  nullable), `partner_lab_bookings` (state machine; report links to Phase 5
  `health_records`).
- Insurance: `partner_insurance_products` (partner-declared coverage text),
  `partner_insurance_policies` (patient-held references from real submissions),
  `partner_insurance_claim_details` (1:1 with a claim).
- Integrations: `partner_integrations` (API keys stored ONLY as SHA-256 hash +
  prefix; webhook endpoints https-only), `partner_webhook_events` (append-only
  ledger; unique `event_id`; stays PENDING without a delivery worker).
- Finance (architecture only): `partner_settlements` (amounts nullable until a
  real finance action records them; unique settlement period),
  `partner_commissions` (configuration rows; nothing applies them).
- Notifications: `partner_notifications` (IN_APP real; external channels stay
  honest `provider_not_configured`).

Totals after Phase 8 (verified on PostgreSQL 16): **67 tables**; 11 new
feature flags (`partner_*`, all OFF by default). Alembic head
`b4f8d2a6c9e1`. Six partial unique indexes enforce: one active membership per
(org, user), unique registration number per type where present, unique claim
number per org where present, unique active lab test code per org, unique
settlement period per org, unique webhook event ids.

## Indexing

Foreign keys used in filters are indexed (`user_id`, `session_id`, `specialty_id`, …);
`audit_logs.created_at` is indexed for the admin log query; Phase 5 adds
`health_records(patient_id)`, `health_record_shares(record_id, grantee_user_id)`,
and `health_record_access_events(record_id, created_at)`.
