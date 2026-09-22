# MediSave AI — Security

## Implemented

- **Auth**: JWT access (30 min) + refresh (7 d) tokens; refresh endpoint rejects access tokens (tested). bcrypt (rounds 12) password hashing.
- **RBAC**: server-side `require_roles()` dependency on every protected admin/flag route; 10 system roles; new users can only receive PATIENT at registration (tested); role grants audited.
- **Ownership checks**: consents, AI sessions, emergency events/contacts enforce `user_id == current_user.id` (tested with cross-user 404s).
- **Audit logging** (spec §37): LOGIN, LOGIN_FAILED, REGISTER, CONSENT_CHANGE, AI_INTERACTION, AI_CONSENT_BLOCKED, SOS_REQUESTED/CANCELLED, ADMIN_CHANGE, ROLE_CHANGE. Never logs passwords/OTP/tokens.
- **Input validation**: Pydantic v2 schemas with bounds on every request body; consent types validated against the fixed enum.
- **Feature-flag gates**: AI and SOS are kill-switchable server-side (tested → 503).
- **Provider verification** (Phase 3): `verification_status` changes only through the admin decision endpoints, which write an immutable history row + audit entry; booking requires VERIFIED doctors; registration numbers are excluded from public projections; hospital emergency availability is advertised only when separately verified.
- **Secrets**: only via env vars (`MEDISAVE_*`); `.env` git-ignored; `.env.example` committed; no credentials in code or alembic env.
- **CORS**: explicit allow-list from settings (no wildcard with credentials).
- **Rate limiting** (Phase 3): in-process sliding-window limiter on `/auth/*` (10/min/IP) and `/ai/chat` (20/min/IP), disabled under `MEDISAVE_ENV=test` for deterministic tests, unit-testable directly. Single-process scope — multi-instance deployments must front it with a gateway/Redis limiter.

## Frontend rules

Admin/mobile treat stored tokens as opaque; no role-based logic is trusted client-side; the demo banner cannot be dismissed.

## Planned hardening

Refresh-token rotation + revocation list (`jti` is already embedded in tokens), account lockout backoff, HTTPS-only deployment (see DEPLOYMENT.md), security headers middleware, dependency auditing (`pip-audit`, `npm audit`) in CI.
