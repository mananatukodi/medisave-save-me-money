# Digital Health Vault (Phase 5) — Architecture & Data Integrity

The Health Vault is a patient-controlled store for healthcare documents:
create → upload → view/download via short-lived signed URLs → share with
explicit, revocable, time-bounded consent → audit every sensitive access.

Core principle:

```
PATIENT OWNS THE RECORD
        ↓
SECURE STORAGE (encrypted at rest, opaque keys)
        ↓
CONSENT-CONTROLLED ACCESS (scopes + expiry + revocation)
        ↓
AUDIT TRAIL (every view / denial / share / download-url)
        ↓
AUTHORIZED HEALTHCARE PROVIDER
```

## 1. Data model

| Table | Purpose | Key columns |
| --- | --- | --- |
| `stored_files` | file metadata + opaque object key | `owner_id`, `object_key` (never exposed via API), `mime_type`, `size_bytes`, `checksum_sha256`, `storage_provider`, `encryption_metadata`, `upload_status` |
| `health_records` | patient document metadata | `patient_id` (owner), `category`, `title`, `record_date`, `file_id` (nullable FK, `SET NULL` on file deletion), `status`, `created_by`, `deleted_at` |
| `health_record_shares` | consent grants | `record_id`, `grantee_user_id`, `scope` (VIEW_RECORD / VIEW_CATEGORY / DOWNLOAD_RECORD), `purpose`, `expires_at`, `revoked_at` |
| `health_record_access_events` | per-record audit | `record_id`, `actor_user_id`, `action` (VIEW / DOWNLOAD_URL / FILE_UPLOADED / RECORD_CREATED / RECORD_DELETED / SHARE_CREATED / SHARE_REVOKED), `result` (ALLOWED / DENIED) |

Consent is explicit, scoped, time-bounded, revocable, and audited. There is no
role that automatically gains clinical access: DOCTOR sees a record only with
an active, non-expired, non-revoked share whose scope covers the request;
SUPPORT_AGENT and HOSPITAL_ADMIN have no default access; SUPER_ADMIN has **no
ordinary clinical path** — the admin surface is aggregate metrics only.

## 2. Storage abstraction

`app/services/storage.py` defines `StorageProvider` with:

- `put(owner_id, filename, content, mime) -> StoredObject` — encrypts with
  Fernet (envelope key from `MEDISAVE_VAULT_ENCRYPTION_KEY`), stores under an
  opaque UUID object key, returns checksum + size.
- `open(object_key) -> bytes` — decrypts for authorized streaming.
- `signed_url(object_key, ttl) -> str` — HMAC-signed, time-limited (default
  300 s) local URL served by `/health-records/files/{token}`.

Providers are structured so production can swap in S3/MinIO without touching
the service layer. The database stores **object keys, never URLs or paths**.
No public bucket URLs exist anywhere in the system.

### Upload validation (never trust the client)

- MIME allow-list (PDF, PNG, JPEG, WEBP) and extension cross-check.
- Magic-byte sniffing of actual content (`%PDF`, PNG/JPEG/WEBP headers).
- Hard size cap (`MEDISAVE_VAULT_MAX_FILE_MB`, default 10 MB).
- Filename sanitization; path traversal is impossible (keys are UUIDs).
- SHA-256 checksum stored with the file.
- Duplicate detection by checksum (per owner) — the API returns the existing
  record linkage instead of silently storing twice.
- Upload status lifecycle (`COMPLETED` on success); a storage failure leaves
  no orphan metadata.
- Malware scanning is **not** implemented — documented production dependency
  (see §7). Files are stored encrypted and never executed.

## 3. Authorization model

Access to a record requires **exactly one** of:

1. ownership (`record.patient_id == actor.id`),
2. an active share (not revoked, not expired, scope covers the action:
   `VIEW_RECORD`/`VIEW_CATEGORY` for reads, `DOWNLOAD_RECORD` for
   download URLs).

Everything else → `404` for strangers (existence hiding, no IDOR) or `403`
with a `DENIED` audit event where the relationship exists but the
scope/consent fails. Revocation is immediate at the application layer.
Signed-URL generation requires `DOWNLOAD_RECORD` scope or ownership; the
signed token itself is independent of the share and expires quickly —
**revoking a share cannot recall bytes already downloaded**; documented
limitation.

## 4. Audit model

Every sensitive operation writes `health_record_access_events` (record-scoped)
and, where applicable, the global `audit_logs` trail: record created/deleted,
file uploaded, view allowed/denied, download-url issued, share created,
share revoked. Audit rows contain actor/patient/action/result/timestamp and
request metadata — **never document contents, titles, or lab values**.

## 5. Order-independent guarantees (PostgreSQL-verified)

- Deleting a record purges its stored file; a `stored_files` row cannot be
  deleted while still referenced (`fk_health_records_file_id_stored_files`).
- `SET NULL` on `file_id` means file loss never cascades into deleting the
  patient's record metadata.
- Shares and access events die with their record; unrelated patient data is
  never touched by cascades.

## 6. AI integration

`RECORD_SUMMARY` is a navigation intent only: it explains what the vault can
do, requires the patient's own authorization, and never fabricates values.
Automatic AI processing of document contents is **not implemented** — the
honest current answer states that AI document summarization requires the
patient's explicit per-use authorization and is a production dependency.

## 7. Production dependencies & honest limitations

| Item | Status |
| --- | --- |
| Local encrypted storage + signed URLs | IMPLEMENTED (dev-verified) |
| S3/MinIO production storage driver | REQUIRES PRODUCTION INTEGRATION (interface ready) |
| Malware scanning of uploads | REQUIRES PRODUCTION INTEGRATION |
| Revocation of already-downloaded files | IMPOSSIBLE BY DESIGN — documented |
| HIPAA / GDPR compliance | REQUIRES SECURITY + LEGAL REVIEW — not claimed |
| AI document summarization with per-use consent | REQUIRES INTEGRATION |
| KMS-backed envelope keys / key rotation | REQUIRES PRODUCTION INTEGRATION |

Compliance or "fully encrypted at rest with managed keys" claims are **not**
made: encryption is application-side Fernet in this build; production
requires KMS, key rotation, backup encryption, and a security review.
