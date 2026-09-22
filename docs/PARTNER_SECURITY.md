# MediSave AI — Partner Security (Phase 8)

## Threat model

The partner layer introduces the first multi-tenant surface in MediSaveAI.
The dominant risks are cross-organization access (BOLA/IDOR), privilege
escalation through role confusion, stale-member access, suspended-partner
operations, and credential leakage. All are addressed server-side and tested.

## Organization isolation (mandatory on every query)

- Authorization scope derives from the caller's ACTIVE `OrganizationMember`
  row for the organization in the request path. A client-supplied
  `organization_id` in a body is NEVER used for authorization.
- Stranger access → **404** (existence hidden, no enumeration — same contract
  as vault/family ownership 404s).
- Known organization with inactive/revoked membership → **403** (explicit,
  audited denial — distinct from the existence-hiding 404).
- Verified in tests: org A cannot read/list/submit/modify org B's organization,
  members, documents, services, lab tests, bookings, or claims; a partner
  cannot inject rows into another organization by changing path ids.

## RBAC layering

1. Platform roles (PATIENT, DOCTOR, HOSPITAL_ADMIN, PHARMACY_ADMIN,
   LAB_ADMIN, INSURANCE_PARTNER, SUPER_ADMIN, …) gate *who can hold partner
   accounts and who administers* — unchanged from Phases 1–7.
2. Partner roles (PARTNER_OWNER/ADMIN/MANAGER/STAFF/BILLING/SUPPORT) gate
   *what a member may do inside the organization*. The grants each role may
   give are constrained; PARTNER_OWNER is fixed to the creator and can never
   be changed or removed.
3. Organization state gates *whether the organization may act at all*:
   protected operations require APPROVED; SUSPENDED/REJECTED/DEACTIVATED
   partners are blocked server-side.
4. SUPER_ADMIN bypass applies to admin governance endpoints only — and every
   admin decision is audited. SUPER_ADMIN has no automatic access to patient
   clinical content (unchanged Phase 5 rule).

## Least privilege

- Staff cannot add/remove members or decide claims; only owner/admin can
  manage members; only owner/admin/billing/manager roles can decide claims.
- Document verification, lifecycle decisions, and lab-test verification are
  SUPER_ADMIN-only; partners cannot self-verify.
- Admin routes use the existing `require_roles("SUPER_ADMIN")` dependency —
  non-admins receive 403 even with valid tokens.

## Credential security

- API keys are generated as `msk_<token_urlsafe(32)>`; the raw key is returned
  exactly once and never persisted, logged, or included in listings.
- Storage is SHA-256 hash + 12-character prefix (lookup only, not secret).
- Verification is constant-time (`secrets.compare_digest`); tampered or
  unknown keys fail closed.
- Revocation sets status REVOKED; verification checks ACTIVE rows only.
- Webhook endpoints must be `https://` (enforced, 422 otherwise).

## Input validation & integrity

- Pydantic v2 schemas with length/range/enum bounds on every partner payload.
- Lifecycle/claim/booking status changes are state-machine-enforced — clients
  cannot set arbitrary statuses; invalid transitions return 409.
- Claim/registration numbers and lab codes are unique per organization via
  partial unique indexes — only where values exist (nothing invented).
- Duplicate ACTIVE memberships are impossible (partial unique index).

## Audit

Every sensitive action writes an append-only `audit_logs` row:
`PARTNER_ORG_REGISTERED`, `PARTNER_ORG_UPDATED`, `PARTNER_ORG_STATUS`,
`PARTNER_MEMBER_ADDED/UPDATED/REMOVED`, `PARTNER_DOCUMENT_UPLOADED`,
`PARTNER_DOCUMENT_DECISION`, `PARTNER_SERVICE_CREATED/UPDATED`,
`PARTNER_LAB_TEST_CREATED`, `PARTNER_LAB_TEST_DECISION`,
`LAB_BOOKING_REQUESTED`, `LAB_BOOKING_STATUS`, `PARTNER_CLAIM_CREATED`,
`PARTNER_CLAIM_STATUS`, `PARTNER_API_KEY_CREATED`,
`PARTNER_INTEGRATION_REVOKED`, `PARTNER_WEBHOOK_REGISTERED`. Rows carry
actor, role, outcome, and bounded detail — never secrets or document contents.

## Feature-flag containment

All `partner_*` flags default OFF; gated routes return 503. External
integrations (payment settlement, SMS/email/push, webhook delivery workers,
KYC registries, ambulance dispatch) stay OFF and honestly NOT_CONFIGURED
until configured — nothing silently activates.

## Rate limiting & abuse

Partner routes ride the existing in-process limiter on public catalog reads
(`rate_limit_search`); admin and portal routes inherit auth-level controls.
State machines + unique constraints bound duplicate-spam effects.

## Security verification summary

| Threat | Result |
|---|---|
| Org A reads org B org/members/documents/services | 404 existence-hidden (tested + smoke) |
| Org A submits/approves into org B | 404 |
| Body-supplied organization_id swap | ignored — scope from path+membership (tested) |
| Stale (revoked) member access | 403 explicit, audited (tested) |
| Staff escalates to admin functions | 403 (members, claims, documents) (tested) |
| Partner self-verifies documents/tests | 403 (SUPER_ADMIN only) (tested) |
| Suspended partner operates | 403 on protected operations (tested) |
| Invalid lifecycle/claim/booking transition | 409 (tested) |
| Owner role takeover | 409 immutable/irremovable (tested) |
| API key leakage | hash-only storage; raw shown once (tested + smoke) |
| Webhook downgrade to http | 422 (tested) |
| Unverified test/price shown publicly | hidden until VERIFIED (tested + smoke) |
| Claim auto-approval | impossible — 409 DRAFT→APPROVED; human decisions only (tested) |
| Settlement amount fabrication | amounts nullable; no computation path exists (tested) |
| Notification delivery without provider | FAILED provider_not_configured (honest ledger) |
| Admin access unaudited | every decision audited (tested) |
