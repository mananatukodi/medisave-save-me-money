# MediSaveAI V1 architecture

MediSaveAI uses a patient-centred modular monorepo. The runnable web shell in this repository is the patient app foundation; production services are separated so no user interface can bypass authorization or consent.

```text
apps/web (patient experience) ─┐
apps/mobile (React Native)     ├─> services/api (REST /api/v1)
apps/admin                     │       ├─ domain modules + policy checks
apps/hospital-portal           │       ├─ PostgreSQL repositories
                                │       ├─ Redis rate limits / queues
                                │       └─ S3-compatible document adapter
services/ai-service            ─┘
services/notification-worker ───> push / email / SMS adapters
```

## Core boundaries

* **UI:** accessible, localized presentation and loading/error/empty states.
* **API:** versioned request validation, authentication, pagination and structured errors.
* **Domain:** appointments, consent, health records, care discovery and savings rules.
* **Data:** PostgreSQL transactions, soft deletes, immutable audit events and encrypted object references.

## Initial screen map

Patient: Home; My Health; My Care; Documents; My Money; Family; Emergency; Notifications; Settings & Privacy; AI assistant; search results; doctor/hospital/room/ambulance/scheme/lab/medicine/eye-care detail; appointments; telemedicine waiting room; records timeline; bill analyzer; cost calculator; insurance navigator.

Professional and operations: doctor dashboard/profile/availability/queue/consultation; hospital profile/departments/rooms/beds/verification; admin users/providers/schemes/audits/support; super-admin role management.

## Safety and data quality

The API labels all external facts `verified`, `provider_supplied`, `user_supplied`, `estimated`, or `ai_generated`, with source and freshness metadata. No provider ranking, live availability, eligibility, coverage, or saving is inferred. AI responses are educational, disclose uncertainty, never prescribe, and immediately direct emergencies to local emergency services.
