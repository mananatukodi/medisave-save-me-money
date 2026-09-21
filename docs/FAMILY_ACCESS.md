# Family Accounts & Caregiver Access (Phase 6)

Status: **implemented and verified** (see `PHASE_6_VERIFICATION_REPORT.md`).

## Principle

**A FAMILY RELATIONSHIP ≠ ACCESS.** Adding someone as a family member grants
them nothing. The record owner grants explicit, **scoped, time-bounded,
revocable** consent; the Health Vault authorization path re-checks that
consent on **every single request**, so revocation and expiry take effect
immediately.

Default state of a new relationship: **zero clinical access**.

## Reuse, not a parallel system

Family access deliberately reuses the existing trust machinery:

- **Consent rows** live in the dedicated `family_access_consents` table with
  the same shape of guarantees as vault shares (scope + category filter +
  expiry + revocation) — grants/updates/revocations are owner-only and
  audited (`FAMILY_CONSENT_GRANTED` / `FAMILY_CONSENT_REVOKED`).
- **Record access** flows through the existing `authorize_access()` in
  `vault_service.py`: owner → direct share → **family-consent branch**.
  Share logic is untouched; family is a third, strictly-scoped branch.
- **Appointments** use the existing `create_appointment`; family booking is
  expressed as on-behalf-of, not as a transfer of ownership.
- **Audit** uses the existing append-only `audit_logs` plus per-record
  `health_record_access_events` (DENIED rows included).

## Accounts vs. profiles

The pre-existing `family_members` table stores **declared profiles without
accounts** (no login). Phase 6 relationships live in
`family_relationships` and may target either an existing MediSaveAI user
(by email or user id → `member_user_id`) or an emailed invitation that is
bound to the accepting account. Only account holders can authenticate, so
**only account holders can ever exercise access**.

Relationship types (`SPOUSE, PARENT, CHILD, SIBLING, GRANDPARENT,
GRANDCHILD, CAREGIVER, OTHER`) are **user-declared and never verified** —
there is no legal-guardianship or identity verification in Phase 6
(documented production blocker; requires legal review).

## Invitations

- Token: `secrets.token_urlsafe(32)`, stored **only as a SHA-256 hash**,
  shown exactly once to the inviter, never logged, never re-exposed in any
  list endpoint.
- TTL: 24 hours, single use. Accepting twice → 409. Expired → 410.
- Acceptance binds the relationship to the accepting account; a stranger
  accepting someone else's invitation → 403.
- Status machine: `INVITED → ACTIVE` (accept) / `DECLINED` (decline) /
  `EXPIRED` (TTL) / `REVOKED` (either side, immediate).

## Consent scopes (server-enforced allow-list)

`VIEW_HEALTH_RECORDS` · `VIEW_APPOINTMENTS` · `VIEW_MEDICINE_ORDERS` ·
`REQUEST_APPOINTMENT` · `REQUEST_REFILL` · `RECEIVE_HEALTH_ALERTS`

- Never auto-granted; unknown scopes → 422.
- Optional `category_filter` (comma-separated record categories) restricts
  vault visibility to those categories only.
- Optional expiry (`expires_in_days`); re-granting replaces the previous
  consent (single active consent per relationship).

## Authorization flow (Health Vault)

```
authorize_access(record, user, required_scope):
  owner            -> full access (unchanged)
  share holder     -> share rules (unchanged)
  family member    -> ACTIVE relationship?
                      + ACTIVE consent?
                      + VIEW_HEALTH_RECORDS in scopes?
                      + record.category in category_filter?
                      -> allow (VIEW only; downloads stay owner/share)
  everyone else    -> 404 (existence hidden, no IDOR)
```

Related-but-unauthorized → **403** with an audited
`FAMILY_RECORD_ACCESS_DENIED`; total strangers → **404** (unchanged).

## Appointments on behalf of the owner

`POST /api/v1/appointments` accepts `on_behalf_of_patient_id`. The server
verifies an ACTIVE relationship + `REQUEST_APPOINTMENT` consent, then sets:

- `patient_user_id` = **the actual patient (owner)** — ownership never
  transfers,
- `requested_by_user_id` = **the family member (actor)**.

Audited as `APPOINTMENT_BOOKED` with `on_behalf_of=…` detail.

## Medicine orders

`GET /api/v1/orders?for_patient={owner_id}` for a family member requires an
ACTIVE relationship + `VIEW_MEDICINE_ORDERS` consent. The response is the
owner's order list; **order detail and prescription content stay
owner/pharmacy-only** (404 for family members). Audited as
`FAMILY_MEDICINE_ORDERS_VIEWED`.

## AI

The `FAMILY_RECORD_SUMMARY` intent explains the consent requirement in
te/en/hi and **never retrieves or summarizes another person's records** —
the AI is not an authorization bypass.

## Admin governance

`GET /api/v1/admin/family/overview` (SUPER_ADMIN) returns aggregate counts
(active/pending/declined/expired/revoked, access-denied events) and recent
family audit actions. It exposes **no names, no emails, no consent purposes,
no clinical content**. The admin Family Governance page renders exactly
these aggregates.

## Endpoints

| Method | Path | Who |
|---|---|---|
| POST | `/family/invitations` | owner (token returned once) |
| GET | `/family/invitations` · `/family/invitations/received` | owner / invitee |
| POST | `/family/invitations/{id}/accept` · `/decline` | invited account |
| GET | `/family/relationships` · `/family/relationships/{id}` | owner or member |
| POST | `/family/relationships/{id}/revoke` | owner or member (self-remove) |
| GET | `/family/relationships/{id}/consent` | owner or member |
| PUT | `/family/relationships/{id}/consent` | owner only |
| DELETE | `/family/relationships/{id}/consent` | owner only |
| GET | `/family/access-granted-to-me` | member |
| GET | `/family/access-history` | actor's own family audit rows |

## Flutter

Owner screen **My Family** (`/family`): invite (one-time code dialog),
grant/revoke consent, remove member. Member screen **Family Access**
(`/family/access`): accept/decline received invitations, access granted to
me. Localized in te/en/hi. Source complete; **not compiled — Flutter SDK
unavailable on this machine**.
