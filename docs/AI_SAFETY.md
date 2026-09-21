# MediSave AI — AI Safety

The AI Health Assistant is **not a doctor** and never claims to be (spec §3, §38).

## Pipeline (spec §11) — implemented in `app/ai/engine.py`

```
Authentication → Consent check → Emergency/Safety screening → Intent classification
→ Guidance rendering → Safety validation → Structured response → Navigation/action → Audit
```

**Important ordering:** emergency screening runs **before** the consent gate so a user without
AI_ACCESS consent still receives emergency guidance (verified by tests).

## Emergency screening

Trilingual (EN/TE/HI) red-flag phrase matching with two tiers:

- `EMERGENCY` — chest pain, unconscious, not breathing, severe bleeding, stroke signs, seizure, poison, suicidal ideation, snake bite, anaphylaxis, …
- `URGENT` — high fever, vomiting blood, worst-ever headache, infant fever, …

Emergency responses: urgency `EMERGENCY`, red flags listed, `requiresHumanReview: true`,
advice to call **108 (India)** / go to the nearest hospital, navigation to SOS + nearby hospitals.
**Never** claims an ambulance was dispatched (tested).

## Structured response (spec §11 shape)

```json
{
  "intent": "EYE_CARE",
  "urgency": "ROUTINE",
  "message": "...",
  "disclaimer": "This is general health information, not a diagnosis. ...",
  "redFlags": [],
  "recommendedActions": [],
  "navigation": [{"label_en": "...", "label_te": "...", "label_hi": "...", "route": "/specialties/eye-care"}],
  "requiresHumanReview": false,
  "confidence": 0.8
}
```

The mandatory disclaimer is present in all three languages (tested).

## Anti-diagnosis guarantees

- `DISALLOWED_CLAIM_PATTERNS` validator rejects drafts asserting "you have X", "definitely",
  guaranteed cures/outcomes/claim approvals, or telling users to stop medication.
- `enforce_safe_text()` neutralizes violations before return (tested).
- The guidance engine fabricates **no** prices, providers, or records (tested: no ₹/INR amounts).

## Intent set

All 28 spec §10 intents are implemented in `app/ai/intents.py` with EN/TE/HI keyword signals and a
deterministic classifier; an LLM classifier may replace `classify_intent` behind the same interface.

## AI memory (spec §31)

Currently **no** long-term memory is stored beyond session messages (user-visible AI session rows
and audit events). Language preference is stored on the user profile only. Scoped memory is a
Phase 9 feature and will be consent-gated.

## LLM integration status

`MEDISAVE_AI_PROVIDER=none` (default) — deterministic guidance engine, no external calls.
Any LLM = `REQUIRES INTEGRATION` (implement `AIProvider` in `app/ai/providers.py`, keep it behind
this pipeline, add safety tests for its outputs, never ship user health data to a provider without
consent + DPA).
