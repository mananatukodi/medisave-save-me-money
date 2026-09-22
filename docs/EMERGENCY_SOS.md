# Emergency & SOS (Phase 7)

Status: **implemented and verified** (see `PHASE_7_VERIFICATION_REPORT.md`).

## Safety principle

**EMERGENCY SOS NEVER DEPENDS ON AI.** SOS creation is deterministic CRUD +
state machine + audit. AI may route a user to SOS after its (deterministic,
keyword-based) emergency screening, but AI can never create, delay, decide,
or confirm an emergency. The system never claims:

- "ambulance dispatched" — unless a real provider integration confirms it,
- "call connected" — the device dialer reports only CALL REQUESTED,
- "notification delivered" — without a configured provider the ledger says
  FAILED with `provider_not_configured`,
- hospital beds/ICU/doctors-on-duty/ETA — always `NOT_VERIFIED`,
- medical facts — unknown values are literally `UNKNOWN`.

These honesty states are enforced in code and asserted by tests
(`tests/test_emergency_phase7.py`) and live HTTP smoke (70/70).

## State machine

```
REQUESTED (initial; spec "CREATED")
  -> ALERTING | HANDOFF_PENDING | CANCELLED | FALSE_ALARM | FAILED
ALERTING
  -> CONTACTING | HANDOFF_PENDING | CANCELLED | FALSE_ALARM | FAILED
CONTACTING
  -> ACTIVE | HANDOFF_PENDING | CANCELLED | FALSE_ALARM | FAILED
ACTIVE
  -> HANDOFF_PENDING | RESOLVED | CANCELLED
HANDOFF_PENDING
  -> HANDED_OFF | FAILED
HANDED_OFF
  -> RESOLVED
Terminals: CANCELLED, FALSE_ALARM, RESOLVED, FAILED (immutable)
```

- Transitions exist **only** in `emergency_service.ALLOWED_TRANSITIONS`;
  invalid ones raise 409. Clients can never set status directly.
- `ACTIVE` requires real-world confirmation (provider status or hospital
  handoff acceptance) — never a timer or an AI opinion.
- `RESOLVED` is reachable only from ACTIVE/HANDED_OFF; early exits are
  CANCELLED (with reason USER_CANCELLED/DUPLICATE/OTHER) or FALSE_ALARM.
- Records are never deleted; the full audit trail survives.

## Idempotency & duplicate protection (race-safe)

- `POST /emergency/sos` accepts an optional `idempotency_key`. Same user +
  same key returns the **same event** (HTTP 200) — protected by the partial
  unique index `uq_sos_idempotency (user_id, idempotency_key) WHERE key IS
  NOT NULL`; concurrent duplicates are resolved by catching the
  IntegrityError and returning the winner.
- The partial unique index `uq_patient_active_sos (user_id) WHERE status IN
  (non-terminal)` guarantees at most ONE active SOS per patient at the
  database level.
- Without a key, a retry while a non-terminal SOS exists returns that
  existing event (200) — **legitimate emergency retries are never
  rejected**; abuse is bounded by the one-active-SOS constraint, not by a
  rate limiter.

## Minimum-necessary disclosure

The emergency medical summary (`GET /emergency/{event_id}/medical-summary`)
contains ONLY patient-entered profile fields: blood group, allergies,
critical conditions, critical medications, emergency notes. Missing values
are `UNKNOWN`. Access:

- **owner**: always (audited);
- **family member**: ACTIVE Phase 6 relationship + an explicit
  `EMERGENCY_MEDICAL_SUMMARY` consent granted by the patient to
  `family:<relationship_id>` — re-checked on every request; revoked or
  expired consent denies immediately (404, existence hidden);
- **everyone else**: 404 (no IDOR).

Location is shared with a family member only with an explicit
`EMERGENCY_LOCATION` consent. Family alert payloads never include vault
content — only patient display name, event id, status, type, timestamp.

## Family / caregiver alerts

On SOS creation the server notifies (IN_APP ledger) every ACTIVE Phase 6
family member whose consent includes `RECEIVE_HEALTH_ALERTS`, and records
notification attempts for the patient's active emergency contacts
according to their channel preferences — IN_APP is real (SENT); SMS/push/
email without a configured provider are recorded FAILED
`provider_not_configured`, never SENT/DELIVERED. Members read alerts via
`GET /emergency/family-alerts`.

## Nearby emergency hospitals

`GET /emergency/hospitals/nearby?lat&lng&radius_km` (auth required — no
public location data) returns VERIFIED hospitals with
`emergency_available=true`, nearest first, with `availability_status:
"NOT_VERIFIED"`. The response schema has no fields for beds/ICU/doctors/ETA
because the system does not track them.

## Ambulance abstraction

`AmbulanceProvider` protocol (`request_dispatch / get_dispatch_status /
cancel_dispatch`) with an honest default: `NOT_CONFIGURED` —
"Ambulance integration is not currently available." Every attempt is
recorded in `emergency_provider_events` and audited
(`AMBULANCE_REQUESTED`, outcome DENIED for NOT_CONFIGURED). A
`MockAmbulanceProvider` exists for automated tests only
(`settings.ambulance_test_provider`), and the `AMBULANCE_INTEGRATION`
feature flag stays OFF until a real provider is wired.

## Hospital handoff

`POST /emergency/{event_id}/handoffs` (owner) creates HANDOFF_REQUESTED
against a VERIFIED hospital and moves the event to HANDOFF_PENDING. Only
the owning HOSPITAL_ADMIN can ACCEPT/REJECT (`POST
/emergency/handoffs/{id}/decision`); acceptance flips the event to
HANDED_OFF and stamps `confirmed_by_provider="hospital:<id>"` — a real
confirmation, never simulated. Hospital A cannot decide hospital B's
handoff (403).

## Offline / low-connectivity behavior

The Flutter UI keeps the distinctions explicit: "Call requested on your
device" ≠ "SOS event created on MediSaveAI server" ≠ "Emergency service
contacted" ≠ "Ambulance dispatched". If the API is unreachable, the app
says so (honest load-failure states) and the deterministic SOS endpoint
plus idempotency keys make retries safe. No fabricated server status is
ever displayed.

## Feature flags

Core SOS runs with all optional integrations off: `SOS_ENABLED` gates the
core flow; `EMERGENCY_HOSPITAL_SEARCH`, `EMERGENCY_NOTIFICATIONS`,
`EMERGENCY_LOCATION`, `AMBULANCE_INTEGRATION`, `HOSPITAL_HANDOFF`,
`EMERGENCY_SMS`, `EMERGENCY_VOICE` gate optional capabilities
(integration adapters report NOT_CONFIGURED until providers exist).

## Production integrations still required

SMS gateway, push notification provider, voice/telecom integration,
maps/geocoding provider, ambulance dispatch network (e.g. 108),
hospital network/EMR handoff integration, real-time availability feeds.
All are adapter points behind the documented interfaces; none are faked.
