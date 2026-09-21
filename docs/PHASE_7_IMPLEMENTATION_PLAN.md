# Phase 7 Implementation Plan — Emergency & SOS + Emergency Healthcare Navigation

## Safety principle (non-negotiable)

EMERGENCY SOS NEVER DEPENDS ON AI. The SOS path is deterministic CRUD +
state machine + audit. AI may route a user to SOS after classification, but
AI cannot create, delay, decide, or confirm an emergency. The system never
claims: ambulance dispatched, hospital availability, hospital acceptance,
call connected, or notification delivered unless a real integration
confirms it. Unavailable truth is reported as
`UNKNOWN / NOT_VERIFIED / UNAVAILABLE / NOT_CONFIGURED`.

## Current architecture findings (inspection results)

- **Existing emergency module (Phase 1 level)**: `EmergencyEvent`
  (`REQUESTED/PROCESSING/CONFIRMED/FAILED/CANCELLED`, note, lat/lng strings,
  `confirmed_by_provider`), `EmergencyContact` (name/phone/relationship/
  is_primary). Routes: `POST /emergency/sos`, `GET /emergency/events`,
  `POST /emergency/events/{id}/cancel`, contacts list/add/delete. Flag
  `SOS_ENABLED` (503 when off). Tests assert: auth 401, creation status is
  REQUESTED (never CONFIRMED), owner-only cancel, double-cancel 409, contacts
  CRUD. **All of these contracts must keep passing.**
- **Hospitals** already carry `emergency_available`, `emergency_verified`,
  `latitude/longitude`, `verification_status` — nearby discovery reuses this
  table; no duplication.
- **Consents** table is type/recipient/scope/expiry based
  (`CONSENT_TYPES` enum) — emergency scopes extend this enum additively.
- **Family access (Phase 6)**: ACTIVE relationship + consent scopes
  (`RECEIVE_HEALTH_ALERTS` already allow-listed); relationships are
  re-checked per request.
- **Audit**: append-only `audit_logs` via `record_audit`; per-resource
  correlation via `resource_type`/`resource_id`.
- **RBAC**: role_ids on User; admin routes enforce SUPER_ADMIN server-side.
- **Rate limiting**: sliding-window limiter per route-group in `main.py`,
  disabled in tests via `MEDISAVE_RATE_LIMIT_ENABLED=false`/env.
- **Admin React**: page-per-domain convention with aggregate-only governance
  pages (Vault/Family).
- **Flutter**: riverpod + dio ApiClient + go_router + 3-locale ARBs
  (`te/en/hi`); AppLocalizations generated (`generate: true`).
- **Alembic head**: `3f8a91c4d7e2` (Phase 6).

## Reuse map (no parallel systems)

| Need | Reuses |
|---|---|
| SOS identity | auth `CurrentUser` |
| Patient/family gating | Phase 6 `family_service` + consents table |
| Emergency medical summary gating | consents (`EMERGENCY_*` types) |
| Nearby hospitals | `hospitals` table (verified + emergency flags) |
| Handoff hospital identity | `hospitals.id` FK |
| Audit | `record_audit` (+ new action names) |
| Flags | `feature_flags` table |
| Admin governance | admin router + React governance-page pattern |

## Scope

### 1. Database (one additive migration `eb7a41c2f901_phase_7_emergency_sos`)

- **`emergency_events` (extend)**: add `emergency_type`, `initiated_by_user_id`
  FK (patient when self-initiated), `idempotency_key`,
  `location_timestamp`, `network_status`, `device_platform`,
  `correlation_id`, `initiated_at`, `cancelled_at`, `resolved_at`,
  `cancel_reason`, `resolved_by_user_id`. `user_id` remains the patient
  (= spec's `patient_user_id`). Existing columns untouched.
- **Partial unique index** `uq_patient_active_sos`: at most one non-terminal
  event per patient (`status IN (REQUESTED, ALERTING, CONTACTING, ACTIVE,
  HANDOFF_PENDING)`).
- **Partial unique index** `uq_sos_idempotency`: one event per
  (user_id, idempotency_key) where the key is not null.
- **`emergency_profiles` (new)**: one row per user (unique), all fields
  optional — `blood_group` (UNKNOWN when unset), `allergies`,
  `critical_conditions`, `critical_medications`, `emergency_notes`,
  `preferred_hospital_id` FK, `organ_donor_status`,
  `accessibility_needs`, timestamps.
- **`emergency_handoffs` (new)**: event FK, hospital FK,
  `requested_by_user_id` FK, status `HANDOFF_REQUESTED/ACCEPTED/REJECTED/
  EXPIRED/COMPLETED`, requested/responded/completed timestamps, notes.
- **`emergency_notifications` (new)**: event FK (nullable), contact FK
  (nullable), `recipient_user_id` (nullable), `recipient_phone`,
  `channel` (IN_APP/PUSH/SMS/EMAIL), `status` (QUEUED/SENT/DELIVERED/FAILED),
  `provider_name`, `error_detail`, `sent_at`.
- **`emergency_provider_events` (new)**: event FK, `provider_name`,
  `action` (DISPATCH_REQUESTED/DISPATCH_STATUS/DISPATCH_CANCELLED),
  `status`, `detail`, `created_at` — an append-only provider ledger.
- **`emergency_contacts` (extend)**: `priority` (int), `active` (bool),
  `notification_preferences` (string), `updated_at`. `is_primary` kept for
  backward compatibility.

### 2. State machine (service-enforced, never client-supplied)

```
REQUESTED (initial; spec "CREATED")
  -> ALERTING | CANCELLED | FALSE_ALARM | FAILED
ALERTING
  -> CONTACTING | CANCELLED | FALSE_ALARM | FAILED
CONTACTING
  -> ACTIVE | HANDOFF_PENDING | CANCELLED | FALSE_ALARM | FAILED
ACTIVE
  -> HANDOFF_PENDING | RESOLVED | CANCELLED
HANDOFF_PENDING
  -> HANDED_OFF | FAILED
HANDED_OFF
  -> RESOLVED
Terminals: CANCELLED, FALSE_ALARM, RESOLVED, FAILED
```

`ACTIVE` requires a real-world confirmation (ambulance provider status or
handoff acceptance) — the API alone never advances an event to ACTIVE on a
timer or AI opinion. Invalid transitions → 409.

### 3. SOS creation, idempotency, dedup

- `POST /emergency/sos` accepts optional `idempotency_key` (≤64 chars) plus
  location snapshot (optional, timestamped, accuracy-aware), `emergency_type`,
  `network_status`, `device_platform`.
- Same user + same key → **returns the same event** (200) — verified against
  the partial unique index; concurrent inserts are resolved by catching the
  IntegrityError and re-reading.
- Without a key, if the patient already has a non-terminal SOS → the
  **existing event is returned (200)** — legitimate retries are never
  punished; abuse is bounded by the one-active-SOS constraint.
- Correlation id: server-generated UUID per event, echoed in audit rows.

### 4. Cancel / false alarm / resolve

- `POST /sos/{id}/cancel` (and legacy `/events/{id}/cancel`) with optional
  reason `USER_CANCELLED|FALSE_ALARM|DUPLICATE|OTHER`; `FALSE_ALARM` reason
  drives status `FALSE_ALARM`. Ownership enforced (owner or
  family-with-consent actor is NOT allowed to cancel — cancellation is
  patient/admin only; support/SUPER_ADMIN via admin path with audit).
- `POST /sos/{id}/resolve` — patient or SUPER_ADMIN; terminal RESOLVED.
- Records are never deleted; terminal states are immutable.

### 5. Emergency contacts (extend)

`PATCH /emergency/contacts/{id}` (name/phone/relationship/priority/active/
preferences), delete keeps 204, list ordered by priority then created.
Strict owner-scoping (404 for others).

### 6. Emergency profile (minimum-necessary data)

`GET/PUT /emergency/profile` — patient-managed, all optional. Summary
endpoint `GET /emergency/{event_id}/medical-summary` returns ONLY
explicitly provided fields; missing → `"UNKNOWN"`; disclosure gated by:
owner, or ACTIVE family relationship + active
`EMERGENCY_MEDICAL_SUMMARY` consent granted by the owner to
`family:<relationship_id>` (Phase 6 relationship re-checked per request;
revoked/expired → 403). Profile access audited
(`EMERGENCY_PROFILE_ACCESSED`).

### 7. Family/caregiver alerts

On SOS creation, for each ACTIVE Phase 6 relationship where the owner
granted the member `RECEIVE_HEALTH_ALERTS`, an `emergency_notifications`
row (channel IN_APP, status SENT) is created for the member, plus an audit
`EMERGENCY_CONTACT_NOTIFIED`. Minimum necessary: patient full name, event
id, status, created_at, emergency_type — location included ONLY if the
owner granted the member an active `EMERGENCY_LOCATION` consent. Members
read their alerts via `GET /emergency/family-alerts`. Full vault content is
never exposed.

### 8. Location handling

Optional, client-supplied snapshot with `location_timestamp` + accuracy;
stored on the event only; never in list responses for other users; family
visibility governed by `EMERGENCY_LOCATION` consent; admin sees presence
boolean, not coordinates. `GET /emergency/family-alerts` omits location
unless consent exists. Audit `LOCATION_CAPTURED` when stored.

### 9. Nearby emergency hospitals

`GET /emergency/hospitals/nearby?lat&lng&radius_km` — auth required (no
public location data). Returns VERIFIED hospitals with
`emergency_available=true`, haversine distance, and honesty fields:
`emergency_verified` (bool), `availability_status="NOT_VERIFIED"` — no
beds/ICU/doctors-on-duty/ETA ever returned. Flag `EMERGENCY_HOSPITAL_SEARCH`.

### 10. Ambulance abstraction

`AmbulanceProvider` protocol: `request_dispatch() / get_dispatch_status() /
cancel_dispatch()`. Implementations: `NoAmbulanceProvider` (default —
returns `NOT_CONFIGURED`, nothing is faked) and `MockAmbulanceProvider`
(explicitly test-only, selected via settings in tests). Dispatch requests
are recorded in `emergency_provider_events` and only advance an event when
the provider reports a real status. Flag `AMBULANCE_INTEGRATION`; without a
configured production provider the API answers
"Ambulance integration is not currently available."

### 11. Notifications abstraction

`emergency_notifications` rows + `notification_service.queue_and_send()`.
IN_APP is real (rows are the inbox). SMS/push/email without a configured
provider → status FAILED with `error_detail="provider_not_configured"`
(never SENT/DELIVERED). Flags `EMERGENCY_NOTIFICATIONS`, `EMERGENCY_SMS`.

### 12. Hospital handoff

`POST /emergency/{event_id}/handoffs` (patient or SUPER_ADMIN) creates
HANDOFF_REQUESTED for a verified hospital; only the hospital-side
confirmation (future integration/admin action) can ACCEPT → event becomes
HANDOFF_PENDING→HANDED_OFF per state machine. No auto-acceptance, ever.
Flag `HOSPITAL_HANDOFF`.

### 13. AI integration

Existing emergency screening (deterministic keyword screener, bypasses
consent) is unchanged. EMERGENCY responses gain navigation actions
`OPEN SOS` + `CALL EMERGENCY SERVICES` (route `/emergency`) — routing only;
AI has no capability to create SOS, and its response text keeps the
no-certainty/no-prescription rules. New/updated AI tests assert the
emergency response includes the SOS action and never treatment claims.

### 14. RBAC matrix (server-enforced)

| Role | Emergency access |
|---|---|
| PATIENT | own SOS CRUD, own contacts, own profile, resolve/cancel own |
| Family member | minimal alerts + medical summary ONLY via ACTIVE relationship + explicit EMERGENCY_* consents |
| DOCTOR | none by default (unchanged) |
| HOSPITAL_ADMIN | handoffs for their hospital only (confirm/reject) |
| SUPPORT_AGENT | operational metadata via admin overview only |
| SUPER_ADMIN | governance overview + resolve on active events (audited) |

### 15. Admin

`GET /admin/emergency/overview` — aggregates: status counts, active count,
recent events (no notes/coords), notification delivery counters, handoff
counts, ambulance provider status (CONFIGURED/NOT_CONFIGURED), denied
access events. `EmergencyGovernancePage.tsx` mirrors the governance-page
pattern.

### 16. Feature flags

Keep `SOS_ENABLED` (core). Seed: `EMERGENCY_HOSPITAL_SEARCH`,
`EMERGENCY_NOTIFICATIONS`, `AMBULANCE_INTEGRATION`,
`HOSPITAL_HANDOFF`, `EMERGENCY_LOCATION`, `EMERGENCY_SMS`,
`EMERGENCY_VOICE`. Core SOS + contacts + profile work with all optional
flags off.

### 17. Rate limiting

Emergency router keeps the existing per-IP auth limiter only where it does
not gate retries; SOS creation itself is deduplicated by idempotency +
one-active-SOS constraint instead of rejection. No new hard limiter on
`POST /sos`.

### 18. Flutter

Screens in `lib/features/emergency/`: EmergencyHomeScreen (large SOS
button + confirm), SOSActiveScreen (status, CALL EMERGENCY SERVICES via
`tel:` intent, call contact, nearby hospitals, cancel), ContactsScreen,
ProfileScreen, NearbyHospitalsScreen, HistoryScreen, HandoffScreen.
Telugu-first strings; honest device-vs-server distinction
("Call initiated on device" ≠ "SOS created on server" ≠ "Ambulance
dispatched"). Home tile stays prominent. **Source only — no compile
claims (Flutter SDK unavailable).**

### 19. Tests (new `tests/test_emergency_phase7.py` + extended
`test_emergency.py`)

State machine (valid/invalid), idempotency (same-key same-event,
concurrent), active-dedup, cancel/false-alarm/resolve, contacts
priority/active, profile get/put + UNKNOWN honesty, medical-summary
consent gating (family with/without consent, revoked, expired), family
alerts + location consent, nearby hospitals (auth, verified filter,
NOT_VERIFIED, no fabrication), handoff lifecycle + hospital scoping,
ambulance NOT_CONFIGURED honesty, notification provider-not-configured
honesty, audit presence, IDOR matrix, AI emergency intent routes to SOS.

### 20. Known limitations / production integrations required

SMS provider, push provider, voice/telecom, maps/geocoding provider,
ambulance dispatch network (e.g. 108), hospital EHR/handoff integration,
real-time hospital availability feed. All are adapter points, feature-
flagged, and honestly reported as NOT_CONFIGURED until integrated.

## Rollout

1. Migration (additive) → 2. service + routes → 3. tests → 4. admin →
5. Flutter → 6. smoke + integrity checks → 7. docs + verification report.
Feature flags default: core on, integrations off.
