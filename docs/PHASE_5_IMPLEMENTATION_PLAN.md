# Phase 5 Implementation Plan — Digital Health Vault

Status: planning complete → implementation follows the order in §23 of the
Phase 5 specification. This document records what exists today and exactly
what Phase 5 adds on top of it.

## 1. Repository inspection (what already exists and is reused)

### Backend (FastAPI, `backend/app/`)
- **Auth/JWT**: `security/jwt.py` (access 30 min / refresh 7 d), `security/deps.py`
  (`get_current_user`, `CurrentUser`, `require_roles`, `record_audit`, `client_ip`).
- **RBAC roles** (seeded): PATIENT, FAMILY_MEMBER, DOCTOR, HOSPITAL_ADMIN,
  PHARMACY_ADMIN, LAB_ADMIN, INSURANCE_PARTNER, SUPPORT_AGENT, FIELD_AGENT,
  SUPER_ADMIN.
- **Consent model** (`models/consent.py`): `Consent(user_id, consent_type,
  purpose, data_scope, recipient, duration_days, granted_at, revoked_at,
  expires_at)` with `is_active` property. Existing types: AI_ACCESS,
  DOCTOR_ACCESS, HOSPITAL_ACCESS, FAMILY_ACCESS, INSURANCE_ACCESS,
  DOCUMENT_SHARE. Endpoints: list / grant / revoke under `/api/v1/consents`.
  → **Phase 5 extends this model, no duplicate consent system.**
- **Audit** (`models/ops.py::AuditLog`): append-only, indexed on action and
  created_at; helper `record_audit(db, action=…, actor_user_id=…,
  resource_type=…, resource_id=…, outcome=…, detail=…)`.
- **Models**: users/RBAC, consents, AI sessions/messages/events, specialties,
  providers (doctors/hospitals + verifications), appointments, pharmacies/
  medicines/prices/orders (Phase 4), emergency events, feature flags.
- **Migrations**: `c916d59c142b` (core) → `ffff2f1bd46e` (Phase 3) →
  `2a34b8868e53` (Phase 4). Dev convenience: `Base.metadata.create_all` on
  SQLite only.
- **Rate limiting**: sliding-window limiters (auth/AI/search) with
  `MEDISAVE_RATE_LIMIT_ENABLED` switch.
- **Tests**: 142 passing (conftest provides isolated SQLite + seeded roles +
  `make_user`/`login_headers` helpers).
- **Dependencies available after this phase's addition**: `python-multipart`
  (multipart uploads), `cryptography` (AES-GCM envelope encryption).

### Admin (React+TS+Vite, `admin/`)
Pages: Dashboard/audit, Verification Queue (doctors/hospitals), Doctors,
Hospitals, Specialties, Appointments, Medicines, Pharmacies, Price
Verification, Medicine Orders, Feature Flags. Phase 5 adds a **records
governance** page (aggregate/security events only — no document contents).

### Flutter (`mobile/`)
Clean-architecture features with Riverpod + GoRouter; l10n ARBs (te/en/hi);
screens for home/AI/SOS/doctors/hospitals/appointments/medicines/orders/
pharmacies/settings. Phase 5 adds the Health Vault feature package.

### Docker/Postgres
`docker-compose.yml` (postgres:16 + backend), volume persisted, currently on
migration head `2a34b8868e53`.

## 2. Gap analysis → Phase 5 additions

| Area | Today | Phase 5 adds |
|---|---|---|
| Document storage | none | `StorageProvider` abstraction + local encrypted-at-rest provider (Fernet, AES-128-CBC+HMAC under the hood via `cryptography`) and MinIO/S3 provider skeleton behind env config |
| Health records | none | `health_records`, `stored_files`, `health_record_shares`, `health_record_access_events` tables + migration |
| Consent scoping | coarse types | share-level scope (`VIEW_RECORD`/`DOWNLOAD_RECORD`/`VIEW_CATEGORY`), grantee binding, expiry, revocation — reusing `Consent` where type fits, and `health_record_shares` as the record-scoped grant |
| Record access control | none | service-layer authorization: owner, active share, expired/revoked/wrong-scope denial, audited DENIED events |
| Signed URLs | none | short-lived (≤15 min) token-based download URLs via `itsdangerous`-style HMAC signing using the app secret; denied when share revoked |
| Admin | dashboards only | storage/records governance metrics (no document content) |
| AI | navigation only | `RECORD_SUMMARY` intent stub with consent gate and honest "not implemented" processing — no automatic record ingestion |
| Localization | te/en/hi core | vault terminology in all three languages |

## 3. Design decisions

1. **Storage**: `StorageProvider.put/get/delete/delete_many` interface.
   `LocalEncryptedStorage` (dev) encrypts bytes with a key derived from
   `MEDISAVE_VAULT_ENCRYPTION_KEY` (or app secret in dev only) via Fernet and
   stores objects under `data/vault/`. `S3Storage` is structured but requires
   real credentials → REQUIRES PRODUCTION INTEGRATION. DB stores `object_key`
   (opaque), never paths or URLs.
2. **Upload validation**: MIME allow-list + extension allow-list + size cap
   (10 MB) + magic-byte sniffing (PDF/JPEG/PNG/DICM) — client MIME never
   trusted alone. SHA-256 checksum for dedupe detection. Malware scanning:
   marked `scan_status=PENDING` — REQUIRES PRODUCTION INTEGRATION (ClamAV or
   equivalent).
3. **Encryption**: per-file DEK, wrapped by the master key
   (`stored_files.encryption_metadata` holds algorithm + wrapped DEK, never
   the raw key).
4. **Shares = record-scoped consents**: `health_record_shares` rows carry
   grantee_user_id, scope, categories filter, expires_at, revoked_at, and a
   `consent_id` link to the existing `consents` table (type DOCUMENT_SHARE)
   so consent remains one auditable system.
5. **Deletion**: soft delete (`deleted_at`) — files are purged from storage
   only on explicit patient purge; cascade behavior deliberately narrow.
6. **Break-glass**: NOT implemented. SUPER_ADMIN gets aggregate metrics only;
   ordinary admin cannot read records. Documented decision.
7. **AI**: no automatic record ingestion. `RECORD_SUMMARY` intent returns
   honest navigation + consent requirement; processing REQUIRES PRODUCTION
   INTEGRATION (LLM with PHI controls).

## 4. Execution order (per spec §23)

models → migration → storage → services → authz/consent integration → audit →
APIs → tests → PostgreSQL verification → HTTP smoke → admin UI → Flutter →
l10n → docs → regression → verification report.

## 5. Definition of done

All Phase 1–4 tests keep passing; new ownership/RBAC/consent/share/file/URL/
audit/security tests pass; migration verified on SQLite + Docker Postgres;
28-check smoke extended with the Phase 5 flow; admin builds; Flutter authored
(NOT COMPILED — SDK unavailable); no fabricated medical data; honest labels
for everything not implemented.
