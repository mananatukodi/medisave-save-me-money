# MediSave AI — Partner API (Phase 8)

Base URL `/api/v1` · interactive docs at `/docs` · errors follow the platform
contract (401/403/404/409/422/503).

## Quickstart

```bash
# 1) Enable flags (SUPER_ADMIN)
PATCH /api/v1/feature-flags/partner_onboarding   {"is_enabled": true}
# 2) Onboard (any authenticated user; becomes PARTNER_OWNER)
POST /api/v1/partners
{
  "organization_type": "HOSPITAL",          # DOCTOR|HOSPITAL|PHARMACY|DIAGNOSTIC_LAB|INSURANCE|AMBULANCE
  "legal_name": "Example Hospital",          # partner-supplied — never invented
  "display_name": "Example Hospital",
  "registration_number": "",                 # optional; uniqueness enforced only when present
  "city": "Hyderabad"
}
# 3) Submit + admin decision
POST /api/v1/partners/{id}/submit
POST /api/v1/admin/partners/{id}/review     # SUPER_ADMIN
POST /api/v1/admin/partners/{id}/approve    # SUPER_ADMIN
# 4) Operate (services, documents, members, lab, insurance, integrations)
```

## Conventions

- **Organization scoping**: every `/partners/{org_id}/…` route resolves the
  caller's ACTIVE membership for that exact org. Strangers → 404; stale
  members → 403. Body `organization_id` values are never used for authz.
- **Status fields are server-owned.** They change only through the dedicated
  lifecycle/decision endpoints (state-machine enforced, audited).
- **Flags**: routes gated by `partner_*` flags return 503 while disabled.
- **Idempotency**: webhook events carry unique `event_id`s; duplicate ACTIVE
  memberships and duplicate per-org registration numbers/claim numbers/test
  codes are rejected by partial unique indexes.
- **Honesty**: declared prices are UNVERIFIED until admin verification; claims
  never auto-approve; settlement amounts exist only when a finance action
  recorded them; external channels are `provider_not_configured`.

## Endpoint map (summary)

### Partner self-service — `/partners`

| Method | Path | Flag | Notes |
|---|---|---|---|
| POST | `/partners` | partner_onboarding | create DRAFT org + owner membership |
| GET | `/partners/mine` | partner_ecosystem | caller's organizations |
| GET | `/partners/{org_id}` | partner_ecosystem | scoped detail |
| PATCH | `/partners/{org_id}` | partner_ecosystem | update details (status fields ignored) |
| POST | `/partners/{org_id}/submit` | partner_verification | DRAFT→SUBMITTED (re-submit → UNDER_REVIEW) |
| GET | `/partners/{org_id}/history` | partner_ecosystem | append-only lifecycle trail |
| POST/GET | `/partners/{org_id}/documents` | partner_verification | KYC upload/list |
| POST/GET | `/partners/{org_id}/members` | partner_ecosystem | add/list (owner/admin) |
| PATCH/DELETE | `/partners/{org_id}/members/{member_id}` | partner_ecosystem | role change/remove (owner/admin; owner protected) |
| GET/POST | `/partners/{org_id}/services` | partner_services | catalog (requires APPROVED) |
| PATCH | `/partners/{org_id}/services/{service_id}` | partner_services | update; price edit resets verification |
| POST/GET | `/partners/{org_id}/lab/tests` | partner_lab | test catalog (requires APPROVED) |
| POST | `/partners/{org_id}/lab/bookings` | partner_lab | booking for an existing patient (VERIFIED tests only) |
| POST | `/partners/{org_id}/lab/bookings/{booking_id}/status` | partner_lab | booking state machine |
| POST/GET | `/partners/{org_id}/insurance/products` | partner_insurance | product catalog (requires APPROVED) |
| POST/GET | `/partners/{org_id}/insurance/claims` | partner_claims | claims (starts DRAFT) |
| POST | `/partners/{org_id}/insurance/claims/{claim_id}/status` | partner_claims | 9-state machine; decisions human-only |
| GET | `/partners/{org_id}/insurance/claims/{claim_id}/history` | partner_claims | append-only claim events |
| POST | `/partners/{org_id}/integrations/api-keys` | partner_api | raw key shown once (owner/admin) |
| POST | `/partners/{org_id}/integrations/webhooks` | partner_webhooks | https endpoint registration (owner/admin) |
| GET | `/partners/{org_id}/integrations` | partner_webhooks | list — hash/prefix only, never raw keys |

### Partner portal — `/partner`

| Method | Path | Flag | Notes |
|---|---|---|---|
| GET | `/partner/dashboard` | partner_ecosystem | per-org aggregates: services, pending docs, open claims, lab tests/bookings, my role |
| GET | `/partner/notifications` | partner_ecosystem | IN_APP inbox across my organizations |

### Patient-facing

| Method | Path | Flag | Notes |
|---|---|---|---|
| GET | `/lab-tests?organization_id&q&limit` | partner_lab | VERIFIED tests at APPROVED labs only |
| GET | `/insurance/claims` | partner_claims | caller's own claims |
| GET | `/insurance/claims/{claim_id}` | partner_claims | owner-only (404 otherwise) |

### Admin — `/admin/partners` (SUPER_ADMIN)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/partners?status&organization_type` | queue/list |
| GET | `/admin/partners/overview` | aggregates (types, statuses, pending docs, claims, webhook backlog, denied events) |
| GET | `/admin/partners/{org_id}` · `/history` · `/documents` | scoped detail |
| POST | `/admin/partners/{org_id}/review` | UNDER_REVIEW |
| POST | `/admin/partners/{org_id}/approve` | APPROVED (from UNDER_REVIEW / SUSPENDED re-activation path) |
| POST | `/admin/partners/{org_id}/reject` | REJECTED (re-reviewable) |
| POST | `/admin/partners/{org_id}/suspend` | SUSPENDED (blocks operations) |
| POST | `/admin/partners/{org_id}/reactivate` | SUSPENDED → APPROVED |
| POST | `/admin/partners/{org_id}/deactivate` | DEACTIVATED (terminal) |
| POST | `/admin/partners/{org_id}/documents/{doc_id}/decision` | UNDER_REVIEW/VERIFIED/REJECTED/EXPIRED |
| GET | `/admin/partners/lab/tests/queue` | UNVERIFIED test queue |
| POST | `/admin/partners/lab/tests/{test_id}/decision` | VERIFIED/REJECTED |

## State machines

**Organization**
```
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED
UNDER_REVIEW → VERIFICATION_REQUIRED → UNDER_REVIEW
SUBMITTED | UNDER_REVIEW → REJECTED → UNDER_REVIEW
APPROVED → SUSPENDED → APPROVED | DEACTIVATED
any pre-terminal → DEACTIVATED (terminal)
```

**Claim**
```
DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED | PARTIALLY_APPROVED | REJECTED
UNDER_REVIEW → ADDITIONAL_INFORMATION_REQUIRED → UNDER_REVIEW
APPROVED | PARTIALLY_APPROVED → SETTLED (terminal)
DRAFT | SUBMITTED | UNDER_REVIEW | AIR | APPROVED | PARTIALLY_APPROVED → CANCELLED
```

**Lab booking**
```
REQUESTED → CONFIRMED → SAMPLE_COLLECTED → IN_PROGRESS → REPORT_READY → COMPLETED
CANCELLED from REQUESTED/CONFIRMED/SAMPLE_COLLECTED/IN_PROGRESS
```

## Webhook events (ledger)

Event types: `APPOINTMENT_CREATED`, `APPOINTMENT_UPDATED`, `ORDER_CREATED`,
`ORDER_UPDATED`, `CLAIM_UPDATED`, `LAB_REPORT_READY`,
`EMERGENCY_HANDOFF_UPDATED`, `PAYMENT_UPDATED`, `PARTNER_STATUS_CHANGED`.

Deliveries are recorded honestly: PENDING until a real delivery worker exists
(and `partner_webhooks` is enabled); the ledger never fabricates DELIVERED.
Payloads are minimum-necessary references (ids, types, statuses) — never
patient clinical content.
