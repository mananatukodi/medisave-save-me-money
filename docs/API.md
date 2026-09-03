# REST API contract (V1)

All endpoints are versioned below `/api/v1`, JSON, authenticated unless marked public, validated at the boundary, paginated with `page` and `pageSize`, and return `{ data, meta }` or `{ error: { code, message, requestId } }`.

| Module | Representative endpoints |
| --- | --- |
| Auth | `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/otp/verify` |
| Patient 360 | `GET/PATCH /patients/:id`, `GET /patients/:id/timeline`, `GET/POST /patients/:id/documents` |
| Discovery | `GET /doctors`, `/hospitals`, `/rooms`, `/beds`, `/ambulances`, `/labs` |
| Care | `GET/POST /appointments`, `PATCH /appointments/:id/status`, `POST /telemedicine/:appointmentId/session` |
| Savings | `POST /bills`, `GET /bills/:id/analysis`, `POST /savings/cost-estimates` |
| Support | `GET /schemes`, `POST /eligibility/guidance`, `GET /medicines`, `GET /eye-care` |
| Privacy | `GET/POST /consents`, `POST /consents/:id/revoke`, `GET /audit-logs` |

`GET /health` is a liveness endpoint and `GET /ready` confirms database, Redis, and object storage dependencies. Authorization is policy based: a recipient must have an active, unexpired consent containing the requested record scope. Every permitted read of protected data creates an audit event. Appointment creation locks the provider/time slot in a transaction and rejects conflicts with `409 APPOINTMENT_SLOT_UNAVAILABLE`.
