# MediSave AI — API

Base URL: `/api/v1` · OpenAPI: `/docs` (interactive) · spec §23 versioning.

## Health (unauthenticated)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | liveness + `demo_mode` flag |
| GET | `/ready` | DB connectivity check |
| GET | `/version` | name/version/tagline/ai_provider |

## Auth
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/auth/register` | 201 → tokens; new users always PATIENT |
| POST | `/api/v1/auth/login` | 200 → tokens; failure audited |
| POST | `/api/v1/auth/refresh` | refresh token only (access tokens rejected) |
| GET | `/api/v1/auth/me` | profile + roles |

## Users
| Method | Path | Notes |
|--------|------|-------|
| GET/PATCH | `/api/v1/users/me` | profile; language `te\|en\|hi` |
| POST | `/api/v1/users/me/password` | change password |

## AI Health Assistant
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/ai/chat` | body `{message, session_id?, language}`; 403 without AI_ACCESS consent; 503 if `AI_ENABLED` flag off. Returns spec §11 structured response incl. `navigation` actions. Emergency screening bypasses consent. |

## Specialties
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/specialties` | 17 specialties, trilingual |
| GET | `/api/v1/specialties/{slug}` | incl. services (eye-care, dental-care seeded) |

## Consents
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/consents` | own consents |
| POST | `/api/v1/consents` | grant (type enum, purpose, scope, recipient, duration) |
| POST | `/api/v1/consents/{id}/revoke` | owner-only; idempotency guarded |

## Emergency
| Method | Path | Notes |
|--------|------|-------|
| GET/POST | `/api/v1/emergency/contacts` | own contacts |
| DELETE | `/api/v1/emergency/contacts/{id}` | owner-only |
| POST | `/api/v1/emergency/sos` | creates event **REQUESTED**; 503 if flag off |
| GET | `/api/v1/emergency/events` | own events |
| POST | `/api/v1/emergency/events/{id}/cancel` | only REQUESTED/PROCESSING |

## Feature flags
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/feature-flags` | any authenticated user |
| PATCH | `/api/v1/feature-flags/{key}` | SUPER_ADMIN only |

## Admin (SUPER_ADMIN only, server-side)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/admin/users` | paginated |
| POST | `/api/v1/admin/users/{id}/roles` | grant system role; audited |
| GET | `/api/v1/admin/audit-logs` | newest first |
| GET | `/api/v1/admin/feature-flags` | flags view |
| GET | `/api/v1/admin/appointments` | all appointments (Phase 3) |

## Doctors (Phase 3)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/doctors` | search: specialty, city, consultation_type, verification_status, limit/offset |
| GET | `/api/v1/doctors/{id}` | public profile + services + specialty links (registration numbers hidden) |
| GET | `/api/v1/doctors/{id}/availability?date&days` | computed slots with BOOKED/BLOCKED reasons |
| POST | `/api/v1/doctors/register` | DOCTOR role; creates PENDING profile (audited) |
| PATCH | `/api/v1/doctors/me` | doctor updates own profile |
| POST | `/api/v1/doctors/me/services` | create service; declared prices are UNVERIFIED |
| POST | `/api/v1/doctors/me/services/{id}/prices` | declare price (never auto-verified) |
| GET/POST | `/api/v1/doctors/me/availability` | weekly rules (replaces template; audited) |
| POST | `/api/v1/doctors/me/blocks` | holiday/break blocks |

## Hospitals (Phase 3)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/hospitals` | search: specialty, city, verification_status |
| GET | `/api/v1/hospitals/{id}` | public profile |
| POST | `/api/v1/hospitals/register` | HOSPITAL_ADMIN role; PENDING (audited) |

## Providers (Phase 3)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/providers?kind=doctor\|hospital` | unified search with the same filters |

## Appointments (Phase 3)
| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/appointments` | book; VERIFIED doctors only; 409 when slot taken; `on_behalf_of_patient_id` books for a family member (REQUEST_APPOINTMENT consent; `patient_user_id` stays the owner, `requested_by_user_id` = family actor) |
| GET | `/api/v1/appointments?role=patient\|doctor` | scoped to caller |
| GET | `/api/v1/appointments/{id}` | owner (patient or provider) only |
| PATCH | `/api/v1/appointments/{id}` | status transitions per state machine; patients may only cancel |
| POST | `/api/v1/appointments/{id}/cancel` | frees the slot |
| POST | `/api/v1/appointments/{id}/reschedule` | validates the new slot server-side |

## Admin verification queue (Phase 3, SUPER_ADMIN)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/admin/verifications/doctors[?status]` | queue |
| GET | `/api/v1/admin/verifications/hospitals[?status]` | queue |
| GET | `/api/v1/admin/verifications/doctors/{id}/history` | immutable decisions |
| GET | `/api/v1/admin/verifications/hospitals/{id}/history` | immutable decisions |
| POST | `/api/v1/admin/verifications/doctors/{id}/decision` | VERIFIED/REJECTED/UNDER_REVIEW/SUSPENDED; audited |
| POST | `/api/v1/admin/verifications/hospitals/{id}/decision` | same |

## Phase 4 — Medicines, Pharmacies, Prices, Orders

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/medicines` | paginated search (q, dosage_form, prescription_required, status); empty catalog returns `[]` |
| POST | `/api/v1/medicines` | SUPER_ADMIN master data, audited |
| GET | `/api/v1/medicines/{id}` | public identity fields |
| GET | `/api/v1/medicines/{id}/prices` | verified+current provenance rows; `include_all=true` for admin review |
| GET | `/api/v1/medicines/{id}/availability` | verified pharmacies' stock (UNKNOWN stays UNKNOWN) |
| GET | `/api/v1/medicines/{id}/savings` | savings engine; `potential_savings` null unless CALCULATED |
| GET / POST | `/api/v1/pharmacies` | public verified search / PHARMACY_ADMIN registration (starts PENDING) |
| GET | `/api/v1/pharmacies/{id}` | verified pharmacy detail |
| GET/PATCH | `/api/v1/pharmacies/me` | owner profile self-service |
| GET/POST | `/api/v1/pharmacies/me/inventory` | stock upsert |
| POST | `/api/v1/pharmacies/me/prices` | new versioned price (PENDING) |
| GET / POST | `/api/v1/orders` | create with snapshots / own history |
| GET/PATCH | `/api/v1/orders/{id}` | ownership-scoped detail / state transition |
| POST | `/api/v1/orders/{id}/prescription` | patient document-reference submission |
| POST | `/api/v1/orders/{id}/prescription-review` | pharmacy/admin human decision (audited) |
| GET | `/api/v1/admin/pharmacies/verification` | queue by status |
| POST | `/api/v1/admin/pharmacies/{id}/verify\|reject\|suspend\|review` | audited decisions + immutable history |
| GET | `/api/v1/admin/prices/verification` | price queue by status |
| POST | `/api/v1/admin/prices/{id}/decision` | VERIFIED / REJECTED |
| POST | `/api/v1/admin/prices/expire-stale` | VERIFIED → EXPIRED sweep |
| GET | `/api/v1/admin/orders` | order oversight incl. prescription states |
| GET | `/api/v1/admin/vault/overview` | vault governance metrics (aggregate only, no content) |

## Health Vault (Phase 5)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/v1/health-records` | create record metadata (owner = patient) |
| GET | `/api/v1/health-records` | list own records; filters: category, status, date range, title |
| GET | `/api/v1/health-records/{id}` | detail incl. file metadata (object keys never exposed) |
| PATCH | `/api/v1/health-records/{id}` | owner-only metadata edit |
| DELETE | `/api/v1/health-records/{id}` | soft-delete + purge stored file |
| POST | `/api/v1/health-records/{id}/upload` | multipart upload; MIME + magic-byte + size validation; encrypted at rest |
| GET | `/api/v1/health-records/{id}/download-url` | short-lived HMAC signed URL (300 s) |
| GET | `/api/v1/health-records/files/{token}` | signed-URL streaming endpoint |
| POST/GET | `/api/v1/health-records/shares` | create/list consent shares (scope, purpose, expiry) |
| DELETE | `/api/v1/health-records/shares/{share_id}` | revoke — immediate, audited |
| GET | `/api/v1/health-records/shared-with-me` | records shared with the caller |
| GET | `/api/v1/health-records/{id}/audit` | per-record access trail (owner only) |

## Family Accounts & Caregiver Access (Phase 6)

A relationship grants **zero** access; every clinical access is gated by
owner-granted, scoped, revocable consent re-checked per request
(see `FAMILY_ACCESS.md`).

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/v1/family/invitations` | create INVITED relationship; raw token returned **once** (SHA-256 stored); 24 h TTL; 422 self-invite / unknown type; 409 duplicate active |
| GET | `/api/v1/family/invitations` | invitations I sent (no token material) |
| GET | `/api/v1/family/invitations/received` | invitations addressed to my account |
| POST | `/api/v1/family/invitations/{id}/accept` | invited account only (403 otherwise); 410 expired; 409 reuse |
| POST | `/api/v1/family/invitations/{id}/decline` | invited account |
| GET | `/api/v1/family/relationships` | relationships where I am owner or member |
| GET | `/api/v1/family/relationships/{id}` | owner/member only; 404 for strangers |
| POST | `/api/v1/family/relationships/{id}/revoke` | owner or member self-remove; revokes active consent; immediate |
| GET | `/api/v1/family/relationships/{id}/consent` | consent history (owner/member) |
| PUT | `/api/v1/family/relationships/{id}/consent` | owner-only grant/replace; scopes validated against server allow-list; optional `category_filter` + `expires_in_days` |
| DELETE | `/api/v1/family/relationships/{id}/consent` | owner-only revocation, immediate |
| GET | `/api/v1/family/access-granted-to-me` | ACTIVE relationships where I am the member |
| GET | `/api/v1/family/access-history` | my own family audit rows (actions `FAMILY_*`) |
| GET | `/api/v1/orders?for_patient={id}` | family member view of the patient's orders — requires ACTIVE relationship + `VIEW_MEDICINE_ORDERS`; order detail/prescriptions stay owner-only (404) |
| GET | `/api/v1/admin/family/overview` | SUPER_ADMIN governance aggregates + recent family audit actions (no names, no content) |

## Emergency & SOS (Phase 7)

SOS is deterministic (AI-free). Honesty contract: no fabricated dispatch,
availability, call-connection, or delivery — unavailable truth is
UNKNOWN/NOT_VERIFIED/UNAVAILABLE/NOT_CONFIGURED (see `EMERGENCY_SOS.md`).

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/api/v1/emergency/sos` | 201 new event (REQUESTED); 200 returns the SAME event for a repeated `idempotency_key` or while a non-terminal SOS exists — retries never rejected; optional location snapshot + timestamp/accuracy, `emergency_type`, `network_status`, `device_platform` |
| GET | `/api/v1/emergency/sos/{id}` | owner only; 404 hides existence |
| POST | `/api/v1/emergency/sos/{id}/cancel` | reason USER_CANCELLED\|FALSE_ALARM\|DUPLICATE\|OTHER; state-machine enforced; FALSE_ALARM → terminal FALSE_ALARM |
| POST | `/api/v1/emergency/sos/{id}/resolve` | only from ACTIVE/HANDED_OFF (real engagement) |
| GET | `/api/v1/emergency/history` | own events, optional `status` filter |
| GET/POST | `/api/v1/emergency/contacts` | own contacts (priority, active, channel preferences) |
| PATCH/DELETE | `/api/v1/emergency/contacts/{id}` | owner-only update/remove |
| GET/PUT | `/api/v1/emergency/profile` | patient-managed emergency profile (all fields optional) |
| GET | `/api/v1/emergency/{event_id}/medical-summary` | minimum-necessary summary; family requires ACTIVE relationship + EMERGENCY_MEDICAL_SUMMARY consent; missing fields = UNKNOWN; audited |
| GET | `/api/v1/emergency/family-alerts` | minimal alerts for members with RECEIVE_HEALTH_ALERTS; location only with EMERGENCY_LOCATION consent |
| GET | `/api/v1/emergency/hospitals/nearby` | verified + emergency-capable hospitals by distance; `availability_status` always NOT_VERIFIED (no beds/ICU/ETA fabrication) |
| POST | `/api/v1/emergency/{event_id}/ambulance` | provider abstraction; NOT_CONFIGURED unless a real provider is configured; every attempt ledgered + audited |
| GET/POST | `/api/v1/emergency/{event_id}/handoffs` | handoff to a VERIFIED hospital; event → HANDOFF_PENDING |
| POST | `/api/v1/emergency/handoffs/{id}/decision` | owning HOSPITAL_ADMIN accepts/rejects; acceptance is REAL confirmation → event HANDED_OFF |
| GET | `/api/v1/emergency/{event_id}/notifications` | honest delivery ledger (IN_APP SENT; external without provider FAILED provider_not_configured) |
| GET | `/api/v1/emergency/{event_id}/audit` | emergency audit trail (owner or SUPER_ADMIN) |
| GET | `/api/v1/admin/emergency/overview` | SUPER_ADMIN operational aggregates (no notes/coords/content) |

## Partner Ecosystem (Phase 8)

Organization-scoped partner layer (6 partner types). Every partner query is
scoped through an ACTIVE `OrganizationMember` row; strangers get 404
(existence-hidden), stale members get 403. Lifecycle and claim transitions are
service-enforced state machines; every decision is audited. All partner flags
(`partner_*`) are OFF by default — gated routes return 503.

### Partner self-service (`/api/v1/partners`)

| Method | Path | Notes |
|---|---|---|
| POST | `/partners` | onboard; creates DRAFT org + PARTNER_OWNER membership (flag `partner_onboarding`) |
| GET | `/partners/mine` | caller's organizations |
| GET/PATCH | `/partners/{org_id}` | scoped detail/update (owner/admin/manager) |
| POST | `/partners/{org_id}/submit` | DRAFT→SUBMITTED (or →UNDER_REVIEW re-submission) |
| GET | `/partners/{org_id}/history` | append-only lifecycle history |
| POST/GET | `/partners/{org_id}/documents` | KYC documents (10 types; UPLOADED/UNDER_REVIEW/VERIFIED/REJECTED/EXPIRED) |
| POST/GET | `/partners/{org_id}/members` | add/list members (6 partner roles; owner immutable) |
| PATCH/DELETE | `/partners/{org_id}/members/{member_id}` | role change / remove (owner/admin only) |
| GET/POST | `/partners/{org_id}/services` | service catalog; declared prices stay UNVERIFIED |
| PATCH | `/partners/{org_id}/services/{service_id}` | update (price change resets verification) |
| POST/GET | `/partners/{org_id}/lab/tests` | lab test catalog (partner-entered, UNVERIFIED) |
| POST | `/partners/{org_id}/lab/bookings` | booking for an existing patient (VERIFIED tests only) |
| POST | `/partners/{org_id}/lab/bookings/{id}/status` | booking state machine |
| POST/GET | `/partners/{org_id}/insurance/products` | product catalog (coverage text is partner-declared) |
| POST/GET | `/partners/{org_id}/insurance/claims` | claims; starts DRAFT |
| POST | `/partners/{org_id}/insurance/claims/{id}/status` | 9-state claim machine; approvals are human decisions |
| GET | `/partners/{org_id}/insurance/claims/{id}/history` | append-only claim events |
| POST | `/partners/{org_id}/integrations/api-keys` | raw key shown exactly once; SHA-256 hash stored |
| POST | `/partners/{org_id}/integrations/webhooks` | https-only endpoint registration |
| GET | `/partners/{org_id}/integrations` | list (never exposes raw keys) |

### Partner portal (`/api/v1/partner`)

| Method | Path | Notes |
|---|---|---|
| GET | `/partner/dashboard` | aggregates across caller's orgs (counts only, no patient content) |
| GET | `/partner/notifications` | IN_APP inbox (org-scoped; honest statuses) |

### Patient-facing partner endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/lab-tests` | public VERIFIED tests at APPROVED labs only; prices exactly as verified |
| GET | `/insurance/claims` | patient's own claims |
| GET | `/insurance/claims/{id}` | owner-only detail (404 for strangers) |

### Admin partner governance (SUPER_ADMIN)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/partners` | list + status/type filters |
| GET | `/admin/partners/overview` | aggregates: type/status counts, pending docs, claims, webhook backlog, security denials |
| GET | `/admin/partners/{id}` · `/history` · `/documents` | scoped detail |
| POST | `/admin/partners/{id}/review\|approve\|reject\|suspend\|reactivate\|deactivate` | lifecycle decisions (audited + history row) |
| POST | `/admin/partners/{id}/documents/{doc_id}/decision` | UNDER_REVIEW\|VERIFIED\|REJECTED\|EXPIRED (human decision; no automated KYC claimed) |
| GET | `/admin/partners/lab/tests/queue` | lab test verification queue |
| POST | `/admin/partners/lab/tests/{id}/decision` | VERIFIED\|REJECTED |

### Partner state machines

Organization: DRAFT→SUBMITTED→UNDER_REVIEW→APPROVED; VERIFICATION_REQUIRED
side-loop; APPROVED→SUSPENDED→(APPROVED\|DEACTIVATED); REJECTED→UNDER_REVIEW;
DEACTIVATED terminal. Non-APPROVED orgs cannot perform protected operations.

Claims: DRAFT→SUBMITTED→UNDER_REVIEW→{APPROVED\|PARTIALLY_APPROVED\|REJECTED};
ADDITIONAL_INFORMATION_REQUIRED loop; APPROVED/PARTIALLY_APPROVED→SETTLED;
CANCELLED from most states; SETTLED terminal. No automatic approvals.

## Error contract
422 validation (Pydantic detail) · 401 invalid/expired token · 403 role/consent denied ·
404 not found or not owned · 409 conflict · 503 feature disabled.
