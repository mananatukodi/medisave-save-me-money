# Phase 6 Implementation Plan — Family Accounts & Caregiver Access

## Principle

FAMILY RELATIONSHIP ≠ ACCESS. A relationship only enables the owner to grant
explicit, scoped, time-bounded, revocable consent. Default state for a new
relationship: **zero clinical access**. The Health Vault authorization path
remains the final gate for every record access.

## Reuse (no parallel authorization system)

- Consent itself stays in the existing `consents` table (Consent model,
  `CONSENT_CHANGE` audit) — family consents are rows with
  `consent_type="FAMILY_ACCESS"`, `recipient="family:<relationship_id>"`,
  scope + category filter + expiry. No new consent engine.
- Record access flows through the existing `authorize_access` in
  `vault_service.py`: owner → share → family-consent path. Share logic is
  untouched; family is a third, strictly-scoped branch.
- Audit via existing `record_audit` + per-record access events.
- Appointment booking via existing `create_appointment` (owner remains
  `patient_user_id`; family member recorded as requester in notes/audit).

## Key design decision — accounts vs. profiles

The existing `family_members` table stores **declared profiles without
accounts** (no password, no login). Phase 6 invites may target either an
existing MediSaveAI user (by email → `member_user_id`) or an emailed
invitation (profile-only until that person registers; a documented,
honest limitation). Access with scopes requires an **account**: only
users can authenticate. Relationship types: SPOUSE, PARENT, CHILD, SIBLING,
GRANDPARENT, GRANDCHILD, CAREGIVER, OTHER — user-declared, never verified
(requires production identity verification).

## New models (one migration, additive only)

`family_relationships`: id, owner_user_id FK, member_user_id FK nullable,
display_name, relationship_type (8 types), status (INVITED/PENDING/ACTIVE/
REVOKED/DECLINED/EXPIRED), invitation_token_hash (sha256, never raw),
invitation_expires_at, invited_email nullable, accepted_at, declined_at,
revoked_at, timestamps. Unique partial index: one ACTIVE relationship per
(owner, member) pair. Token: `secrets.token_urlsafe(32)`, stored hashed,
24 h expiry, single-use.

`family_access_consents`: id, relationship_id FK, scopes (comma-separated
from a fixed allow-list), category_filter, purpose, granted_by, expires_at,
revoked_at, timestamps. Grant/update/revoke are owner-only, audited.

Family scope allow-list (server-enforced): VIEW_HEALTH_RECORDS,
VIEW_APPOINTMENTS, VIEW_MEDICINE_ORDERS, REQUEST_APPOINTMENT,
REQUEST_REFILL, RECEIVE_HEALTH_ALERTS. Never auto-granted; default none.

## Authorization flow (record access)

`authorize_access`: owner → None (full) → existing share check → **new
family branch**: find ACTIVE relationship (member_user_id == user), find
FAMILY_ACCESS consent for it (active, not expired), require VIEW_HEALTH_RECORDS
in scopes, enforce category_filter, audit `FAMILY_RECORD_ACCESS{,_DENIED}` +
per-record DENIED event. Stranger-with-no-relationship → 404 (unchanged);
related-but-unauthorized → 403 (unchanged convention). Revocation/expiry is
immediate because the check re-queries state on every access.

## API surface (/api/v1/family)

POST/GET `/family/invitations` · accept/decline by id (auth = invitee
account + token knowledge path) · GET `/family/relationships` (owner + member
views) · POST `/{id}/revoke` (owner or member self-remove) · GET/PUT/DELETE
`/{id}/consent` (owner-only; PUT validates scopes against allow-list) · GET
`/access-granted-to-me` · GET `/access-history` (own audit rows as actor).

Appointments: `AppointmentCreate.on_behalf_of_patient_id` (optional). If
present, server verifies ACTIVE relationship + REQUEST_APPOINTMENT consent;
`patient_user_id` = patient; `requested_by_user_id` = actor; audited
`APPOINTMENT_REQUESTED_BY_FAMILY`. Medicine orders: read-side view scoped by
VIEW_MEDICINE_ORDERS for Phase 6 (REQUEST_REFILL scaffolded, honest).

## AI, admin, Flutter

AI: FAMILY_RECORD_SUMMARY guidance intent — explains the consent requirement,
never retrieves/infers. Admin: `/admin/family/overview` aggregates only
(counts + recent family audit actions, no names beyond role labels, no
content) + governance page. Flutter: family screens (owner "My Family" +
member "Family Access") + te/en/hi keys; NOT COMPILED (no SDK).

## Minor/dependent honesty

Architecture stores DOB on profiles but Phase 6 does NOT implement legal
guardian verification; documented as a controlled extension requiring
legal review. No compliance/guardianship claims.
