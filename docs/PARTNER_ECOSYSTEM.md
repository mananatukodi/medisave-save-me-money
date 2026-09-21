# MediSave AI — Partner Ecosystem (Phase 8)

## Overview

The partner ecosystem lets healthcare organizations onboard, get verified, and
operate on MediSaveAI without ever weakening patient ownership or the honesty
contract. Six partner types are supported by ONE architecture:

`DOCTOR · HOSPITAL · PHARMACY · DIAGNOSTIC_LAB · INSURANCE · AMBULANCE`

Future partner types require zero rewrites: `organization_type` is a validated
string enum and all partner behavior is type-generic (profiles are metadata,
services are catalog rows, operations are state machines).

## Architecture

```
USER (auth/RBAC unchanged)
  ↓  ACTIVE OrganizationMember (partner role)
ORGANIZATION (lifecycle: DRAFT → … → APPROVED/SUSPENDED/…)
  ↓  PartnerProfile (typed metadata + links to existing rows)
PARTNER USERS / STAFF (PARTNER_OWNER … PARTNER_SUPPORT)
  ↓  SERVICES / OPERATIONS (services, documents, lab, insurance, integrations)
PATIENT TRANSACTIONS (bookings, orders, claims — patient ownership intact)
```

### Key invariants

1. **Membership grants scope, roles only gate.** A generic platform role never
   grants organization access. Every partner query resolves the caller's ACTIVE
   `OrganizationMember` row for the exact organization in the path.
2. **Providers are linked, never duplicated.** `partner_profiles.doctor_id /
   hospital_id / pharmacy_id` reference the existing Phase 3/4 rows. Booking,
   orders, prescription gating, price provenance, snapshots — all unchanged.
3. **Honesty everywhere.** Declared prices stay UNVERIFIED until a human
   verifies them; claims never auto-approve; settlement amounts stay NULL until
   a finance action records them; external notification channels are
   `provider_not_configured`; webhook events stay PENDING without a delivery
   worker; no automated KYC is claimed.

## Lifecycle

```
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED
UNDER_REVIEW → VERIFICATION_REQUIRED → UNDER_REVIEW
SUBMITTED/UNDER_REVIEW → REJECTED → UNDER_REVIEW (re-review)
APPROVED → SUSPENDED → APPROVED | DEACTIVATED
Any pre-terminal state → DEACTIVATED (terminal)
```

- Every transition writes an append-only `partner_lifecycle_events` row AND an
  audit-log entry. Invalid transitions → 409.
- Only APPROVED organizations may create services/tests/products, accept
  bookings, or appear in public partner discovery.
- SUSPENDED / REJECTED / DEACTIVATED partners cannot perform any
  patient-facing operation (server-enforced, tested).

## Onboarding

1. Registration (`POST /partners`) — creates DRAFT org + PARTNER_OWNER
   membership + profile. All fields partner-supplied; nothing invented.
2. Details/contact updates (PATCH `/partners/{id}`).
3. Document upload (`POST /partners/{id}/documents`) — 10 KYC document types,
   stored through the Phase 5 encrypted storage (`stored_files` FK) or an
   opaque storage reference; never public.
4. Submission (`POST /partners/{id}/submit`).
5. Admin review (`POST /admin/partners/{id}/review`) →
   VERIFICATION_REQUIRED loop if documents are insufficient.
6. Approval / rejection (`approve` / `reject`) — human SUPER_ADMIN decision,
   immutable history, audited.
7. Activation is implicit in APPROVED; deactivation/suspension are explicit
   admin actions.

## Documents / KYC

Statuses: `UPLOADED → UNDER_REVIEW → VERIFIED | REJECTED`, plus `EXPIRED` for
lapsed validity. Records keep `checksum`, `issued_at`, `expires_at`,
`verified_by`, `verified_at`, `review_note`. Verification is a recorded HUMAN
decision — no government-registry integration is claimed.

## Members

Roles: `PARTNER_OWNER` (creator, immutable), `PARTNER_ADMIN`,
`PARTNER_MANAGER`, `PARTNER_STAFF`, `PARTNER_BILLING`, `PARTNER_SUPPORT`.

- Owner/admin manage members; each role can only grant a defined subset.
- Owner cannot be removed or downgraded; duplicate ACTIVE membership → 409
  (partial unique index).
- Removal is a revocation (`is_active=false`, `revoked_at`) — history is kept
  and stale members are explicitly 403'd.

## Services

Each service row: organization, `service_type`, name, description, status,
optional price + currency, `price_verification_status`, `price_source`. Prices
are optional — no fabricated pricing. Editing a price resets verification to
UNVERIFIED (mirrors the Phase 4 price-versioning honesty).

## Lab module

- Catalog: partner-entered tests (code/name/category/sample type/preparation/
  optional price), UNVERIFIED until a SUPER_ADMIN verifies them.
- Public discovery (`GET /lab-tests`) shows ONLY verified tests at APPROVED
  labs; nothing is seeded, so an empty catalog is an honest empty catalog.
- Bookings: patient-initiated (public endpoint) or partner-entered references
  for an existing patient. State machine:
  `REQUESTED → CONFIRMED → SAMPLE_COLLECTED → IN_PROGRESS → REPORT_READY →
  COMPLETED`, with CANCELLED from pre-terminal states.
- Reports integrate with the Health Vault through the existing Phase 5
  authorization (record `health_record_id` link) — never a bypass.

## Insurance module

- Products: partner-declared catalogs (`claim_intake_supported` flag).
  Coverage text is never treated as verified truth.
- Policies: patient-held policy references recorded from real submissions.
- Claims: the reusable 9-state machine (DRAFT, SUBMITTED, UNDER_REVIEW,
  ADDITIONAL_INFORMATION_REQUIRED, APPROVED, PARTIALLY_APPROVED, REJECTED,
  SETTLED, CANCELLED). Decisions are explicit human actions with actor,
  timestamps, and optional `approved_amount`; every transition appends to
  `partner_claim_events` and the audit log. Patients see only their own claims.

## Emergency providers

Ambulance/emergency organizations onboard through the same flow. Dispatch
remains strictly behind the Phase 7 `AmbulanceProvider` adapter — production
dispatch stays `NOT_CONFIGURED` until a real provider is configured, and no
fake dispatch state can exist.

## Settlements & commissions (architecture only)

`partner_settlements` records explicit finance actions (period, amounts,
external reference) — the API never computes money and no gateway exists.
`partner_commissions` stores configuration for a future commercial engine;
nothing applies commissions automatically. The `partner_settlement` flag stays
OFF until configured.

## Integrations

- API keys: `msk_`-prefixed raw keys shown exactly once; only a SHA-256 hash +
  12-char prefix is stored; constant-time verification; revocation supported.
- Webhooks: https-only endpoint registration; an append-only event ledger with
  unique event ids (idempotency) records APPOINTMENT_*/ORDER_*/CLAIM_UPDATED/
  LAB_REPORT_READY/EMERGENCY_HANDOFF_UPDATED/PAYMENT_UPDATED/PARTNER_STATUS_CHANGED
  events. Delivery is adapter-based; without a delivery worker events remain
  PENDING and are never marked DELIVERED.
- Notifications: IN_APP is real (the ledger is the inbox); PUSH/SMS/EMAIL are
  recorded honestly as FAILED `provider_not_configured` until providers exist.

## Feature flags (all OFF by default)

`partner_ecosystem`, `partner_onboarding`, `partner_verification`,
`partner_services`, `partner_claims`, `partner_settlement`, `partner_webhooks`,
`partner_api`, `partner_lab`, `partner_insurance`, `partner_emergency`.

Gated routes return 503 while disabled — the same contract as SOS/AI.

## Flutter

Partner administration is deliberately web-based (admin dashboard). The
patient app keeps its existing partner-facing surfaces (find verified doctors,
hospitals, pharmacies; booking; orders; emergency) and can consume the new
public `GET /lab-tests` + patient `GET /insurance/claims` endpoints. Flutter
compile status is documented honestly in the verification report.
