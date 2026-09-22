# MediSave AI — Phase 9 Implementation Plan

> **Status: PLANNING ONLY — IMPLEMENTATION NOT STARTED.**
> Baseline: Phase 1–8 merged to `main` (`00c7a2e473938944ef31bfa9862a5d7085f139d6`), tag `phase-8-complete` → `d2445d4`, CI green, 269/269 backend tests passing. This document plans only; it invents no APIs, tables, providers, prices, availability, insurance data, or production integrations as fact.

**Status labels used throughout:**

- **IMPLEMENTED** — exists in the Phase 1–8 codebase today; must NOT be rebuilt.
- **PARTIAL** — a verified foundation exists; Phase 9 would extend it.
- **NEW** — does not exist; Phase 9 would introduce it inside the existing safety architecture.
- **EXTERNAL DEPENDENCY** — cannot be completed in-code; requires a real vendor contract, credential, or production environment.
- **BLOCKED** — cannot proceed until an external prerequisite is resolved.

---

## 1. Phase 9 Objective

Phase 9 is the next evolution of the verified Phase 1–8 foundation, defined as:

**Scale / Advanced AI / Production Hardening.**

Concretely, Phase 9 exists to:

1. **Extend the AI layer** from a safety-gated, intent-classified, provenance-honest pipeline into an advanced health *assistant*: structured actions, consent-scoped memory, explainable responses, and personalization — without weakening any Phase 1–8 safety, consent, RBAC, audit, emergency, or partner-isolation boundary.
2. **Close platform-hardening gaps** that Phases 1–8 explicitly deferred: distributed rate limiting, refresh-token rotation, webhook background processing, observability, and backup/PITR readiness.
3. **Prepare integration seams** for the external services the platform honestly marks as `REQUIRES INTEGRATION` (LLM, SMS/voice, push, maps, ambulance, payments, S3/KMS/malware scan, KYC) so that each can be enabled by configuration + feature flag when a real contract exists — never by fabricating data.
4. **Keep every honesty invariant intact**: no diagnosis certainty, no prescribing, no fabricated providers, prices, availability, coverage, or savings; emergency handling stays independent of AI consent.

Phase 9 does **not** re-architect the platform, does not migrate to the earlier Codex target architecture (React Native / separate services), and does not claim any integration is live before it is verified.

## 2. Current-State Assessment

Verified facts about the repository at `00c7a2e` (local `main` = `origin/main`, working tree clean):

- **Backend:** FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL. Layering: `app/api/v1` (21 routers), `app/services` (11 modules), `app/models` (12 modules), `app/security`, `app/ai` (pipeline, engine, providers), `app/core` (config, ratelimit, flags). 7 Alembic migrations, the latest being the Phase 8 partner ecosystem migration (`b4f8d2a6c9e1`).
- **Frontends:** `admin/` (React/TypeScript, 15 files under `admin/src`, builds green) and `mobile/` (Flutter, 32 files by the review's counting method — the mobile count is methodology-dependent, not an absolute figure; trilingual ARB localization).
- **Docs:** 26 documents at baseline (before this plan file), including the master implementation plan (which carries the marker **“PHASE 9 — SCALE — NOT IMPLEMENTED”**), `AI_SAFETY.md` (which carries the Phase 9 scoped-memory marker), `API.md` (Phase 1–8 contract), `ARCHITECTURE.md`, and per-phase verification reports.
- **Quality gates at baseline:** 269/269 backend pytest, Ruff clean, 42/42 Phase 8 tests, 73/73 HTTP smoke checks, PostgreSQL migration/integrity verification clean, CI green (backend + admin jobs) after the packaging fix (`40a884d`).
- **Honest architecture markers in code/docs:** external surfaces explicitly marked `REQUIRES INTEGRATION`; the seed layer enforces a no-fabricated-data rule; the SOS layer enforces a no-fabricated-dispatch honesty contract; notification delivery is ledger-based.
- **Known limitations carried from Phase 1–8:** in-process rate limiting, non-rotating refresh tokens, inline (synchronous) webhook sends with no background worker, no metrics/tracing/alerting stack, no PITR/backup runbook, Flutter SDK unavailable in the current development environment (mobile builds blocked), and the test suite runs against SQLite while production targets PostgreSQL (migrations verified on PostgreSQL separately).

**Assessment:** the platform is feature-complete for Phases 1–8 and structurally ready for Phase 9, but it is *not yet production-hardened*, and its AI layer is safety-complete but *capability-thin* relative to the Phase 9 ambition. Both gaps are addressed below.

## 3. Confirmed Phase 1–8 Capabilities

Everything in this section is **IMPLEMENTED**, verified by tests and docs, and must **not** be rebuilt:

| Capability | Verified state |
|---|---|
| **Authentication / RBAC** | Register/login/refresh, JWT-based sessions, role model spanning patients, doctors, hospitals, admins, and partner roles; server-side RBAC enforced per router. |
| **AI safety pipeline** | Ordered pipeline with **emergency screening before the consent gate**; AI access requires the AI consent/flag (403 otherwise); intent classification; explicit-uncertainty outputs; seed and response honesty rules prohibit fabricated data. |
| **Provider discovery / appointments** | Doctor/hospital search, appointment booking with slot-conflict handling (409 semantics). |
| **Medicines / pharmacies / savings** | Medicine and pharmacy catalogs with verified pricing; savings computed only from verified prices (no estimated or invented savings). |
| **Health Vault** | Document upload with signed-URL access and audit trails; storage behind an abstraction (S3/KMS/malware-scan marked `REQUIRES INTEGRATION`). |
| **Family / caregiver access** | Consent-based family model with invitations; caregiver access strictly bounded by granted consent. |
| **Emergency / SOS** | Honesty contract: idempotent SOS creation, explicit state machine, no fabricated dispatch; emergency screening bypasses AI consent as a deliberate safety rule. |
| **Partner ecosystem** | Partner onboarding, KYC document collection (verification itself external), 6 partner roles, lab bookings, a 9-state insurance-claim machine, hashed API keys (SHA-256, stored once), webhook endpoints, admin governance. |
| **Admin governance** | React admin console over governed backend surfaces (partners, claims, flags, audits). |
| **Audit / consent boundaries** | Audit-log model, consent enforcement middleware/service layer, IDOR-scoped queries, trilingual UI/intent baseline (Telugu/English/Hindi), DB-seeded feature-flag architecture, notification ledger. |

## 4. Missing Capabilities

Verified gaps that Phase 9 (or a production prerequisite) must address. None of these exists today as working code:

1. **Live LLM provider integration** — the AI engine has a provider abstraction, but no real LLM is wired (`REQUIRES INTEGRATION`).
2. **Scoped AI memory** — explicitly deferred to Phase 9 in `AI_SAFETY.md`; no memory store exists (**NEW**).
3. **Structured AI actions** — AI cannot propose/execute gated actions; no action-authorization record exists (**NEW**).
4. **Explainability / provenance contract** — **PARTIAL.** The existing `AIResponse` contract (`app/ai/engine.py`) already returns structured fields — `intent`, `urgency`, `message`, `disclaimer`, `red_flags`, `recommended_actions`, `navigation`, `requires_human_review`, `confidence` — with explicit safety/uncertainty semantics. What is missing is per-response **provenance** (record identifiers + source class). Phase 9 must **extend** the existing `AIResponse` contract; it must not introduce a duplicate response structure.
5. **Personalization & recommendations** — depend on scoped memory and provenance metadata (**NEW**).
6. **Distributed rate limiting** — current limiter is in-process (documented known gap); requires Redis or equivalent (**NEW** + **EXTERNAL DEPENDENCY** for the Redis instance).
7. **Refresh-token rotation** — not implemented (**NEW**).
8. **Webhook background processing** — sends are currently inline; no worker/queue/retry (**NEW** + **EXTERNAL DEPENDENCY** for queue infrastructure).
9. **Observability** — no structured-log normalization, metrics, tracing, or alerting stack (**NEW**).
10. **Backup / PITR** — production backup runbook and verification not completed (**NEW** + **EXTERNAL DEPENDENCY** for production database infrastructure).
11. **SMS / voice / push delivery** — notification ledger exists; actual channels are `REQUIRES INTEGRATION`.
12. **Maps / geocoding, ambulance dispatch, payment gateway, S3/KMS/malware scan, government KYC** — all marked `REQUIRES INTEGRATION` in the codebase.
13. **Flutter build availability** — mobile cannot be built in the current dev environment (**BLOCKED** — a current-environment, session-observed condition, not a property of the repository).
14. **External-service failure handling at scale** — per-integration circuit-breaker/fallback behavior is a Phase 9 hardening item (**NEW**).

## 5. Phase 9 Scope

Only the following belong in Phase 9. Each is labeled:

| Candidate area | Status | Phase 9 disposition |
|---|---|---|
| Advanced AI health assistant (multi-turn, structured, safety-preserved conversation) | **PARTIAL → NEW** | Extend the existing safety-gated pipeline; the conversational/session layer is NEW. Live LLM remains an external dependency. |
| Healthcare navigation engine (guide patients to the right verified provider/service) | **PARTIAL** | Build on existing verified provider/pharmacy/lab search; navigation ranks and explains using *verified records only*. |
| Structured AI actions (AI proposes, human authorizes, system executes) | **NEW** | Action-authorization state machine inside existing consent/RBAC/audit boundaries. |
| Scoped AI memory | **NEW** | Explicitly designated Phase 9 scope by `AI_SAFETY.md`; opt-in, per-user, consent-gated, deletable, audited. |
| Explainable AI (per-response provenance + reasoning summary) | **PARTIAL** | `AIResponse` already provides structured fields (intent, urgency, message, disclaimer, red_flags, recommended_actions, navigation, requires_human_review, confidence); Phase 9 **extends** it with provenance/explanation fields — no duplicate response contract. |
| Personalization | **NEW** | Only on top of scoped memory + verified data; strictly consent-gated. |
| Multilingual intelligence | **PARTIAL** | Trilingual UI/intent baseline exists; deepen language handling for AI responses; no invented translation content. |
| Savings guidance | **PARTIAL** | Savings engine exists on verified prices; guidance = explanation layer over verified data only. |
| Provider/partner navigation improvements | **PARTIAL** | Improve discovery/UX over verified records; real-time availability is an external dependency, not Phase 9 scope. |
| Scale / reliability (distributed rate limiting, webhook worker, queue) | **PARTIAL** | In-process `SlidingWindowLimiter` already exists (`app/core/ratelimit.py`); the NEW Phase 9 work is distributed/shared rate limiting, the webhook background worker, and queue coordination; queue infra is an external dependency. |
| Production integrations (LLM, SMS, voice, push, maps, ambulance, payments, S3/KMS/malware, KYC) | **EXTERNAL DEPENDENCY** | Phase 9 delivers *adapter seams + config + flags + contract tests*; live vendors are out of scope until contracts/credentials exist. |
| Observability (logs, metrics, traces, alerts, SLOs) | **NEW** | Core Phase 9 hardening. |
| AI safety hardening (tests, evals, monitoring of safety events) | **PARTIAL → NEW** | Pipeline exists; hardening = systematic adversarial tests + safety-event observability. |
| Emergency/SOS evolution | **IMPLEMENTED** (honesty contract) | Preserve as-is; only observability around it is NEW. |

## 6. Explicit Out-of-Scope Items

The following are **explicitly NOT Phase 9**:

1. **Live vendor onboarding** — signing/enabling any actual LLM, SMS, voice, push, maps, ambulance, payment, S3/KMS, malware-scan, or KYC vendor. Phase 9 builds readiness only.
2. **Real-time hospital/doctor availability feeds** — requires external feeds; excluded.
3. **Any fabricated content** — no invented providers, prices, availability, insurance coverage, savings figures, medical facts, or translation strings beyond what verified data supports.
4. **Diagnosis, prescribing, or medical advice certainty** — permanently out of scope by design.
5. **Architecture migration** — no move to React Native, no split into `services/api` + `ai-service` + `notification-worker` microservices per the earlier Codex target doc; the FastAPI modular-monolith stands.
6. **Mobile store release** — Flutter SDK/build availability is blocked; no release activities.
7. **Payment capture / real claim adjudication** — the 9-state claim machine stays as-is; real money movement is external.
8. **New partner-facing contract changes** — partner APIs keep their Phase 8 shapes (additive provenance metadata only, if any).
9. **CI/CD tooling replacement** — Phase 9 may *extend* CI (per §18) but does not replace the working pipeline.
10. **Bulk analytics / data-science platform** — out of scope; only the observability needed to operate is included.

## 7. AI Safety Architecture

### 7.1 Invariants preserved from Phase 1–8 (non-negotiable)

- **AI is not a doctor.** No diagnosis certainty, no prescribing, no treatment guarantees.
- **No fabricated anything.** Providers, prices, availability, coverage, savings — only verified records, or an explicit “I don't know / not available.”
- **Emergency handling is independent.** Emergency screening precedes the consent gate and never depends on AI consent; SOS dispatch honesty is untouched.
- **Uncertainty stays explicit** in every AI response.
- **Consequential actions require explicit authorization** from the user, through a recorded consent event.
- **Safety checks precede unsafe actions** — always in pipeline order, never after generation.

> Documentation note (MINOR, out of scope for this plan correction): the `app/ai/engine.py` module docstring lists the conceptual order "Consent check → Emergency screening," while actual execution in `run_pipeline` screens for emergencies first (Step 1) before the consent check. The implemented behavior — which this plan assumes and preserves — is the safer ordering; reconciling the docstring is a future code-comment cleanup item, not Phase 9 scope.

### 7.2 Phase 9 advanced-AI pipeline (planning shape)

```
request → intent classification ──→ safety screening (EMERGENCY FIRST, unchanged)
        → consent gating (AI consent + per-feature flags, unchanged semantics)
        → context assembly (scoped memory + user-authorized records + provenance metadata)
        → generation via provider abstraction (live LLM = EXTERNAL DEPENDENCY)
        → response validation (structure, honesty, uncertainty, language)
        → optional action proposal → EXPLICIT user authorization → gated execution
        → audit (session, response, provenance, any action, any memory touch)
```

- **Intent classification:** extends the existing classifier; new intents must pass the same screening.
- **Safety screening:** unchanged position (before consent gate); adds adversarial-input checks.
- **Consent gating:** AI consent plus per-feature flags; no new data class becomes reachable without an explicit grant.
- **Structured response contract:** every AI response carries answer, uncertainty statement, provenance list (record IDs + source class: verified / provider_supplied / user_supplied), and optional proposed action — schema defined at implementation time.
- **Action authorization:** separate record with proposed → authorized → executed/expired/rejected states; execution re-checks RBAC + consent at execution time.
- **Auditability:** every stage transition is auditable; AI reads of health records go through the same access layer as any other read.
- **Provider/data provenance:** each fact in a response is traceable to a stored record or is declared unknown.
- **Failure and fallback behavior:** provider unavailable → honest degradation message + non-AI navigation to existing features; never a fabricated answer; failures are observable safety events.

## 8. Consent and Data-Access Boundaries

Phase 9 AI features interact with protected data only through the existing boundaries:

- **Health records:** AI context assembly reads records exclusively through the same access-control layer used by the API. No AI-specific bypass exists. Every AI read is auditable.
- **Family / caregiver access:** caregiver views are bounded by granted consent, exactly as today. A caregiver's AI session sees only what the family consent model already permits them to see; patient scoped memory is never shared into another user's AI context.
- **Partner data:** partner-supplied records (labs, pharmacies, insurers) enter AI context only as *provenance-labeled* data (`provider_supplied`) that the user is already authorized to see. Partners' own systems are never prompt sources for other users. Organization isolation and partner RBAC are untouched.
- **Emergency data:** SOS state and emergency screening remain independent of AI consent; Phase 9 adds observability around emergency flows, not AI coupling into them.
- **Patient consent:** AI features require the existing AI consent; scoped memory and personalization each require their own explicit, revocable grant. Revocation stops future use and honors deletion requests.
- **Scoped memory:** per-user, opt-in, purpose-limited, size/TTL-bounded, user-viewable and user-deletable, every write/read audited. Memory never stores credentials, full record contents, or third-party personal data.
- **Audit logs:** AI sessions, memory operations, action authorizations, and provenance-bearing responses all produce audit entries; audit access remains admin-governed.

**No Phase 1–8 access boundary is weakened.** Where Phase 9 needs finer granularity (e.g., “allow memory” distinct from “allow AI chat”), it adds *narrower* consent, never broader defaults.

## 9. API Changes Required

Planning level only — no endpoint is invented as final. All items below are **NEW (proposed)** unless marked otherwise, and all mount under the existing versioned API with JWT auth and server-side RBAC:

| Proposed API (theme) | Purpose | Auth | Consent | Data source | Risk | Audit | External dep |
|---|---|---|---|---|---|---|---|
| AI session endpoints (create/list/close a bounded conversation) | Multi-turn assistant within limits | Patient JWT | AI consent + flag | User-authored + authorized records | Medium (safety-gated) | Full session audit | Live LLM |
| Structured AI response fields (provenance, uncertainty, proposed action) | Extend the existing `AIResponse` contract with provenance/explanation fields (no duplicate response contract) | Same as session | Inherits session consent | Verified DB records + provider_supplied labels | Low | Response-level audit | None |
| AI action endpoints (propose → authorize → status) | Human-authorized consequential actions | Patient JWT | Per-action explicit grant | AI proposal + verified targets | High (gated) | Every state transition | Depends on action type |
| Scoped-memory endpoints (view / delete / settings) | User control over AI memory | Patient JWT | Dedicated memory grant | User-scoped memory store | Medium | All memory ops | None |
| Provenance metadata on existing reads (additive fields) | Label record origin | Existing per-router auth | Existing | Existing tables | Low | Existing | None |
| Admin: safety-events & integration-status endpoints | Operational governance | Admin RBAC | N/A (admin scope) | New hardening tables | Medium | Admin audit | None |

**Rules:** no existing endpoint changes its contract (additive fields only); nothing here authorizes cross-tenant access; anything touching an external vendor is flagged `EXTERNAL DEPENDENCY` and stays flag-disabled until §24 prerequisites are met.

## 10. Database Changes Required

Planning level only — **no migrations are created now**. All proposed changes are **additive** (new tables/columns; no destructive change):

- **AI sessions / messages** — bounded conversation records tied to user, consent state, and outcome; retention policy defined at implementation.
- **Scoped AI memory** — per-user entries with purpose tags, TTL/size bounds, and explicit consent reference; cascade-deletable.
- **AI action records** — proposed/authorized/executed/expired/rejected state machine with actor, target, authorization evidence, and result reference.
- **Provenance metadata** — source-class labels (`verified` / `provider_supplied` / `user_supplied`) on records that feed AI context, implemented additively.
- **Recommendation / guidance audit records** — what was recommended, from which verified inputs, shown to whom.
- **Integration status** — an **additive health-status layer over the existing `PartnerIntegration` records** (which already exist, with lifecycle statuses ACTIVE/REVOKED — `PartnerIntegration` is not missing and is not replaced); adds configured/enabled/health state so ops can see seams without code changes.
- **Feature flags** — new flags (AI assistant depth, memory, actions, per-integration enablement) seeded through the existing flag mechanism.

All Phase 1–8 tables, constraints, and data remain untouched; every new structure is nullable/back-fillable so pre-Phase-9 rows remain valid.

## 11. Flutter / Mobile Changes Required

Patient-facing Phase 9 surfaces (all **NEW**, all designed against the existing trilingual, offline-tolerant app):

- **AI assistant screen** — structured responses with visible uncertainty + provenance; emergency escalation surfaces unchanged and independent.
- **Navigation & recommendations views** — ranked from verified records only, with source labels.
- **Consent & memory controls** — grant/revoke AI features, view/delete scoped memory, per-feature toggles.
- **Notification surfaces** — ledger-backed notifications rendered; actual push delivery remains an external dependency.
- **Multilingual UI** — Telugu/English/Hindi via the existing ARB mechanism; no invented strings in this plan (content authored during implementation with review).
- **Offline / low-connectivity behavior** — reuse the existing offline-queue mechanics; AI features degrade honestly (queued or unavailable — never a cached fabricated answer).
- **Safety/error states** — explicit “AI unavailable / uncertain / not medical advice” states for every failure mode.

**Status of the mobile build itself: BLOCKED — a current-environment dependency (session-observed condition).** Flutter SDK/build availability is currently unavailable in the *development environment*; this is an observed environment condition, **not** a property of the repository (the repository contains complete Flutter sources). Mobile implementation can be *authored* but not *built/verified* until the SDK prerequisite is fixed in the environment; accordingly, mobile acceptance criteria cannot be claimed in Phase 9 until unblocked.

## 12. Admin Changes Required

Planning level only (no implementation now). Admin console additions for governance (**NEW**):

- **AI governance** — view active AI feature flags, pipeline configuration versions, and per-feature rollout state.
- **Feature flags** — manage Phase 9 flags through the existing flag architecture (UI may partially exist; deepened as needed).
- **Provider/data provenance** — inspect provenance labels and spot-check AI context composition.
- **Safety events** — review AI safety events (rejected generations, emergency escalations during AI sessions, adversarial-input detections).
- **Integration health** — status of each external seam (configured / enabled / failing) without redeploying.
- **Audit visibility** — richer AI-related audit views within the existing admin-governed audit surface.
- **Operational alerts** — surfacing of §19 alerts to admins.

## 13. Partner Ecosystem Impacts

Phase 9 is deliberately low-impact for partners:

- **Doctors / hospitals / pharmacies / labs / insurance:** no partner-facing contract changes. Their existing onboarding, roles (6 partner roles), lab bookings, and the 9-state insurance-claim machine remain exactly as shipped in Phase 8.
- **Ambulance partners:** SOS honesty contract unchanged; dispatch stays non-fabricated. Any real dispatch integration remains `EXTERNAL DEPENDENCY`.
- **Provenance labeling:** partner-supplied records may gain additive provenance metadata (`provider_supplied`) so AI can cite sources honestly — additive only.
- **Webhooks:** Phase 9's webhook worker (§5) makes partner webhook delivery more reliable (background processing, retries) — an improvement partners benefit from, with the same payloads and signatures.
- **Organization isolation & partner RBAC:** preserved without exception. Partner users' AI/admin surfaces remain scoped to their organization; no AI feature grants cross-organization visibility.

## 14. Notification and External Integration Requirements

| Integration | Current state | Phase 9 disposition |
|---|---|---|
| LLM (AI generation) | Provider abstraction exists; no live provider | **EXTERNAL DEPENDENCY** — adapter seam + contract tests + flag; live vendor out of scope |
| SMS | Ledger exists; no channel | **EXTERNAL DEPENDENCY** |
| Voice | Ledger exists; no channel | **EXTERNAL DEPENDENCY** |
| Push | Ledger exists; no channel | **EXTERNAL DEPENDENCY** |
| Maps / geocoding | Marked `REQUIRES INTEGRATION` | **EXTERNAL DEPENDENCY** |
| Ambulance dispatch | Honesty contract, no dispatch integration | **EXTERNAL DEPENDENCY** |
| Payment gateway | Marked `REQUIRES INTEGRATION` | **EXTERNAL DEPENDENCY** |
| S3 / KMS / malware scan | Storage abstraction with honest limits | **EXTERNAL DEPENDENCY** |
| Government KYC verification | Doc collection implemented; verification external | **EXTERNAL DEPENDENCY** |
| Webhook processing (our side) | Inline sends; no worker/retry | **NEW** — Phase 9 worker/queue/retry implementation (queue infra itself external) |
| Notification ledger | Implemented | **IMPLEMENTED** — preserved; channels plug into it |

Every external seam follows the same rule: **adapter + configuration + feature flag + contract test first; live traffic only after a verified production contract.**

## 15. Security and Privacy Requirements

All existing guarantees are preserved; Phase 9 adds:

- **Zero-trust access** — every new surface re-verifies identity, role, consent, and tenant scope per request (no implied trust from session age).
- **Least privilege** — AI services run with the narrowest data-access roles; scoped memory and action execution use dedicated, minimal permission paths.
- **Consent enforcement** — server-side, per-feature, revocable; consent state is checked at request time and at action-execution time.
- **IDOR prevention** — all new endpoints inherit object-ownership scoping; AI context assembly cannot reach objects the requesting principal cannot read.
- **Secret management** — integration credentials only via environment/config injection; nothing hard-coded; `.env.example` documents required keys without values.
- **Encryption** — in transit everywhere; at rest per existing storage policy; scoped memory treated as sensitive data.
- **Auditability** — AI sessions, memory ops, action transitions, admin changes, and integration enable/disable events are audited.
- **Token rotation** — refresh-token rotation implemented in Phase 9 (detect reuse, invalidate family) — closes the documented Phase 1–8 gap.
- **Rate limiting** — moved to a distributed limiter (Redis-class backend) so limits hold across replicas; AI endpoints get stricter, per-user limits.
- **Replay protection** — idempotency keys (already used in SOS) extended to AI actions and webhook processing.
- **Webhook security** — existing signature scheme preserved; worker adds verification-before-processing, timestamp/replay checks, and poison-message handling.
- **Data minimization** — AI context assembly pulls the minimum fields needed; prompts and memory never carry full documents or credentials.
- **Sensitive-log minimization** — no PHI, tokens, or memory contents in logs; AI prompt/response logging is redacted-by-default and flag-governed.
- **Regulatory compliance review (prerequisite — not performed, not claimed):** a formal legal/compliance review of the AI health-guidance features against **India's Digital Personal Data Protection Act, 2023 (DPDP Act 2023)** and the **Telemedicine Practice Guidelines, 2020** is a Phase 9 prerequisite **before limited production rollout** of AI health guidance. This plan offers no legal conclusions and claims no compliance; it schedules the review (see §24 and the Entry Gate).

## 16. Localization Requirements

- **Languages:** Telugu (`te`), English (`en`), Hindi (`hi`) — continuing the existing trilingual baseline.
- **AI localization:** AI responses honor the user's language preference; language detection/selection rides on the existing request context.
- **Fallback behavior:** if AI-generated content cannot be produced reliably in the requested language, the assistant answers in the language it can support (English fallback) **and says so explicitly** — never a silent language switch, never machine-guessed medical terminology presented as verified.
- **Structured safety text** (uncertainty statements, action prompts, emergency guidance) uses reviewed static translations from the existing ARB pipeline; AI free-text is never the sole carrier of a safety instruction.
- **No invented translation content in this plan**; strings are authored and reviewed during implementation, extending the existing ARBs.

## 17. Testing Strategy

| Test class | Phase 9 requirement |
|---|---|
| Unit tests | New services (memory, actions, provenance, rotation, distributed limiter, webhook worker) at the same rigor as existing services. |
| Integration tests | AI pipeline end-to-end with a *stub* provider; action state machine; memory lifecycle; webhook worker retries. |
| API / contract tests | Every new endpoint: auth, RBAC, consent, validation, additive-compat with existing clients. |
| AI safety tests | Adversarial suite: attempts to elicit diagnoses, prescriptions, fabricated providers/prices/availability/coverage/savings; emergency-screen ordering; uncertainty presence. |
| Consent tests | AI-off → 403; memory revoked → no memory use; per-feature grants enforced; consent checked again at action execution. |
| IDOR / security tests | Cross-user, cross-family, cross-organization, cross-partner access attempts must fail on all new endpoints; memory/action objects are ownership-scoped. |
| Partner-isolation tests | Partner data never enters another organization's AI context; partner RBAC unchanged. |
| Emergency-isolation tests | Emergency screening works with every AI flag off; SOS honesty contract untouched by AI features. |
| Multilingual tests | te/en/hi request handling; fallback behavior asserts explicit language notice. |
| Offline tests (mobile) | Authored where the Flutter SDK permits; queued AI requests resolve honestly on reconnect. |
| External integration contract tests | For each seam: adapter behaves correctly against contract stubs (success, timeout, malformed, outage); live vendors are never required for CI. |
| Load / scalability tests | Distributed rate-limiter correctness under concurrency; webhook worker throughput/backpressure; AI session limits. |
| Regression protection | The existing 269-test suite remains green at every step; Phase 1–8 behaviors are pinned by their current tests plus new additive-contract tests. |

## 18. CI/CD Requirements

No CI changes are made *now*; Phase 9 requires the following evolution (planning level):

- **Backend packaging/install** — already fixed and green (`pip install -e ".[dev]"` with explicit package discovery); keep pinned.
- **Ruff** — extend to cover new modules as they land.
- **pytest** — new suites per §17; keep full-regression as the merge gate; add AI-safety suite as a named, required job.
- **Admin build** — unchanged, extended when admin §12 features land.
- **Mobile build** — add a Flutter build job **only when the SDK prerequisite is resolved** (currently BLOCKED); until then, mobile stays out of CI.
- **Security checks** — dependency audit, secret-pattern scan, and (planning) SAST; fail the build on findings.
- **Migration checks** — run Alembic migrations against a PostgreSQL service in CI (closing the current SQLite-only test-replay limitation for migration verification), plus downgrade-path verification.
- **Artifact checks** — build artifacts contain no secrets, no local paths, no dev data.
- **Reproducibility** — pinned dependency versions; CI installs mirror local and production installs.

## 19. Observability Requirements

Currently absent — Phase 9 introduces (**NEW**):

- **Structured logs** — JSON logs with request IDs, actor/role, route, outcome; redaction rules per §15.
- **Metrics** — request rate/latency/errors per route; DB pool health; **AI-specific**: session counts, generation latency, provider errors, safety-rejection counts, action-authorization funnel; **integration-specific** per-seam success/failure/latency.
- **Tracing** — request-scoped traces spanning API → service → provider calls (including external adapter calls).
- **AI latency/error metrics** — separate SLO candidates for assistant responsiveness vs. safety-check overhead (safety checks are never bypassed for speed).
- **External integration health** — per-seam status endpoint + metrics (feeds §12 admin view).
- **Queue / webhook monitoring** — depth, age, retry counts, poison-message counts.
- **Safety-event monitoring** — every safety rejection or emergency escalation during AI use is a first-class, alertable event.
- **Operational alerts** — paging thresholds for error rates, integration outages, queue backlog, safety-event spikes.
- **Audit trails** — immutable, admin-governed, queryable; the existing audit model extended, not replaced.
- **SLO/SLI considerations** — define SLIs (availability, latency, safety-coverage) during implementation; SLO targets are set with real traffic data, not invented here.

## 20. Rollout and Feature-Flag Strategy

Uses the existing DB-seeded feature-flag architecture (**IMPLEMENTED** foundation):

1. **Dark launch** — new AI modules deployed flag-off; zero behavior change; observability confirms stability.
2. **Internal testing** — flags enabled for internal/admin accounts only; safety-event monitoring tuned.
3. **Limited rollout** — staged enablement (memory → assistant depth → actions last, since actions are highest-risk); per-flag, per-cohort.
4. **Rollback switches** — every Phase 9 feature is independently flag-revertible to Phase 1–8 behavior without deploy.
5. **Dependency gating** — flags for external seams (LLM, channels, storage, KYC) remain off until §24 prerequisites verify; enabling an integration flag without a verified contract is impossible by policy and by config validation.
6. **Emergency disable capability** — a single admin action can disable all AI features instantly (kill-switch flag) while leaving emergency/SOS flows fully functional.

## 21. Migration Strategy

- **Additive schema changes only** — new tables/columns; no renames, no drops, no type narrowing of Phase 1–8 columns.
- **Backward compatibility** — every migration leaves the previous application version fully functional (expand/contract ordering: expand now, contract only in a later, verified phase).
- **Staged data migration** — any backfill (e.g., provenance labels on existing records) runs as separate, resumable, audited steps after the schema lands; partial backfills must leave the system consistent.
- **No destructive migration without verified rollback** — destructive changes are out of Phase 9 scope by policy; if ever required, they demand a tested downgrade path and a backup taken immediately prior.
- **Legacy data protection** — Phase 1–8 rows must remain valid and readable under new constraints (nullable additions, default-safe values); PostgreSQL is the migration-verification target (CI addition per §18), preserving the current SQLite test-replay approach for unit speed while never treating it as migration proof.

## 22. Rollback Strategy

| Change | Rollback |
|---|---|
| AI model/provider | Swap/withdraw provider config via flag; engine falls back to honest unavailability messaging; no code deploy needed. |
| AI prompts/policies | Versioned policy config; revert to prior version by flag/config; changes are audited. |
| Integrations | Per-integration enable flag off; adapter refuses traffic; ledger/queue retains pending items for later drain. |
| Database changes | Additive-only migrations are forward-safe; rollback = application revert to pre-Phase-9 version, which tolerates the extra (nullable) structures; any destructive step (none planned) would require prior backup + tested downgrade. |
| Feature flags | Each feature independently flag-revertible; kill-switch disables all AI at once. |
| Notifications | Ledger persists undelivered items; channel disable queues rather than loses; no silent drops. |
| Mobile release | Server-driven flags make features inert on older clients; mobile rollout (when unblocked) is staged with server-side gating. |
| External provider failures | Circuit-breaker per seam: fail fast, degrade honestly, alert, auto-recover on health; no fabricated fallback data ever. |

## 23. Phase 9 Acceptance Criteria

None of these is claimed as passed — they define *done*:

- **Safety:** 100% of adversarial AI-safety tests pass (no diagnosis certainty, no prescriptions, no fabricated providers/prices/availability/coverage/savings); emergency screening ordering verified under every flag combination.
- **Security:** IDOR suite green across all new endpoints; secret scan clean; refresh-token rotation active with reuse detection; distributed rate limiting enforced across replicas in test.
- **Consent:** AI/memorory/action features return explicit denial without grants; revocation stops use immediately; all consent checks auditable.
- **API correctness:** all new endpoints contract-tested; existing clients unaffected (additive-only diff proven by contract tests).
- **Test coverage:** new-module coverage at parity with existing service standards; full regression (269 + new) green.
- **Regression:** Phase 1–8 test suites, smoke suite (73/73 at baseline), and migration/integrity verification all remain green on PostgreSQL.
- **Integration readiness:** every seam has adapter + contract tests + flag + status reporting, with live vendors still disabled.
- **Observability:** structured logs, metrics, traces, and alerts demonstrably emitted for AI, queue, and integration surfaces; safety events alertable.
- **Localization:** te/en/hi verified for all new surfaces, including explicit fallback notices.
- **Scalability:** load tests show limiter and worker behavior under target concurrency (targets set during implementation from real baselines).
- **Rollback:** kill-switch and per-feature flags demonstrated to revert behavior in a test environment without data loss.
- **Compliance:** the formal legal/compliance review against the DPDP Act 2023 and the Telemedicine Practice Guidelines 2020 is completed and its findings addressed **before** limited production rollout of AI health guidance (the review outcome is not claimed by this plan).

## 24. Dependency / Blocker Matrix

| Area | Status | Dependency | Impact | Resolution/Prerequisite |
|---|---|---|---|---|
| LLM provider | EXTERNAL DEPENDENCY | Vendor contract + API credentials + budget | Advanced assistant cannot generate | Contract signed; adapter config; flag enable after verification |
| SMS / voice | EXTERNAL DEPENDENCY | Telecom/aggregator contract + numbers | Notifications, OTP-style flows stay ledger-queued | Vendor contract; channel adapter; regional compliance |
| Push notifications | EXTERNAL DEPENDENCY | Configured notification/provider credentials and infrastructure (server-side push does **not** inherently require the Flutter SDK; the SDK is needed only to compile/test the mobile client) | Patients get no push alerts (ledger persists) | Provider credentials/infrastructure; Flutter SDK unblock only for mobile-client build/testing |
| Maps / geocoding | EXTERNAL DEPENDENCY | Maps vendor contract | Location search/UX limited to stored data | Vendor contract; adapter + flag |
| Ambulance integration | EXTERNAL DEPENDENCY | Dispatch-partner agreements | SOS stays honest-manual (by design) | Partner agreement; dispatch adapter; drills |
| Payment gateway | EXTERNAL DEPENDENCY | PSP contract + compliance | No real payments (out of scope anyway) | PSP contract; ledger reconciliation design |
| S3 / KMS / malware scan | EXTERNAL DEPENDENCY | Cloud storage + KMS + scan service | Vault stays on local/abstraction storage | Cloud account; key policy; scan pipeline |
| Government KYC | EXTERNAL DEPENDENCY | ID-verification contract | Partner verification stays document-based | Verification vendor; compliance review |
| Regulatory compliance (DPDP Act 2023; Telemedicine Practice Guidelines 2020) | NEW — review prerequisite | Legal/compliance review capacity (external counsel or compliance function) | AI health guidance must not enter limited production rollout without it | Schedule formal legal/compliance review; address findings before rollout-flag enablement |
| Distributed rate limiting | NEW + infra dep | Redis-class store in deployment | Limits don't hold across replicas today | Provision store; implement limiter backend; tests |
| Refresh-token rotation | NEW | None (code-only) | Session-token reuse undetected | Implement + rotate + reuse-detection tests |
| Webhook worker | NEW + infra dep | Queue/worker runtime | Webhook sends are inline (latency + no retry) | Implement worker + retries; provision queue runtime |
| Observability | NEW | Metrics/trace backend choice | No production visibility | Select backend (no vendor ranking here); instrument; alert rules |
| PITR / backups | NEW + infra dep | Production DB infrastructure | No verified recovery point objective | Backup schedule + restore drills; document RPO/RTO |
| Flutter SDK / mobile build | BLOCKED (current-environment dependency, session-observed) | Dev-environment toolchain install | Mobile cannot be built/verified in this environment | Install SDK/toolchain in the environment; then mobile CI job |
| Feature flags | IMPLEMENTED | None | Ready for Phase 9 use as-is | Extend flag set at implementation time |
| Notification ledger | IMPLEMENTED | None | Ready to receive channel adapters | None |
| Audit / consent / RBAC / IDOR boundaries | IMPLEMENTED | None | Must be preserved, not rebuilt | Regression tests keep them pinned |

## 25. Recommended Implementation Order

Dependency-aware sequence (no vendor ranking; no invented timelines — sequencing only):

1. **Prerequisites** — resolve Flutter SDK toolchain (BLOCKED item); provision hardening infrastructure decisions (Redis-class store, queue runtime, observability backend) as *config choices*, not code.
2. **Platform hardening (code-first, no external deps)** — distributed rate limiter; refresh-token rotation; webhook worker/queue with retries; failure-handling (circuit breakers) for existing seams. All behind flags where behavior changes.
3. **AI foundation** — AI session/message model + endpoints; structured response contract (provenance + uncertainty); provenance metadata additive fields; safety-hardening test suite; observability instrumentation for the AI path.
4. **Advanced AI capabilities** — scoped memory (consent-gated, deletable, audited); navigation/guidance over verified records; savings-guidance explanation layer; personalization; multilingual depth; structured actions **last** (highest risk, gated by everything before it).
5. **Integrations** — adapter seams + contract tests + status reporting for LLM, SMS/voice, push, maps, ambulance, payments, S3/KMS/malware scan, KYC; all flag-off; live enablement only on verified contracts.
6. **Mobile / admin enablement** — patient surfaces (assistant, navigation, consent/memory controls, multilingual, offline states) as SDK permits; admin governance views (AI governance, flags, provenance, safety events, integration health, alerts).
7. **Controlled rollout** — dark launch → internal → limited rollout per §20; kill-switch drills; rollback rehearsals.
8. **Production verification** — PITR/backup drills with documented RPO/RTO; load tests; smoke + regression suites; integration flags enabled only where §24 prerequisites verified.

---

### Phase 9 Entry Gate

- **Already ready (IMPLEMENTED, reuse as-is):** auth/RBAC, AI safety pipeline with emergency-first screening and consent gating, provider/appointments, medicines/pharmacies/savings on verified prices, Health Vault with signed-URL + audit, family/caregiver consent, honest SOS, Phase 8 partner ecosystem (onboarding, KYC docs, 6 roles, lab bookings, 9-state claims, hashed API keys, webhooks), admin governance, audit/consent boundaries, feature-flag architecture, notification ledger, green CI, 269/269 regression baseline.
- **Can begin immediately (code-only, no external prerequisite):** distributed rate limiting (given a chosen store), refresh-token rotation, webhook worker, observability instrumentation, AI session/response-contract scaffolding, provenance metadata, the AI-safety adversarial test suite, additive schema design.
- **Must be completed first (before advanced AI ships):** AI foundation (sessions, contract, provenance) before memory; memory before personalization; everything before structured actions; observability before any limited rollout; and a formal legal/compliance review (DPDP Act 2023; Telemedicine Practice Guidelines 2020) before limited production rollout of AI health guidance.
- **Externally dependent (ready-made seams, live use deferred):** LLM, SMS/voice, push, maps/geocoding, ambulance dispatch, payment gateway, S3/KMS/malware scan, government KYC — each requires a real contract + credentials + verification before its flag turns on.
- **Blocked (current-environment condition, session-observed — not a repository property):** Flutter mobile build/verification (SDK/toolchain unavailable in the current development environment); consequently mobile acceptance criteria and any store release.
- **Must remain disabled until production integrations are verified:** every external-integration flag, all live AI generation (until an LLM contract verifies), real dispatch/payment/KYC verification flows, and push/SMS/voice delivery — the platform must continue to behave honestly (ledgered, queued, or explicitly unavailable) while these are off.

### Phase 9 Status

**PLANNING ONLY — IMPLEMENTATION NOT STARTED**
