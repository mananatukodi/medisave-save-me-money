# MediSave AI — Localization

Priority (spec §28): **1. Telugu 2. English 3. Hindi**. No hardcoded user-facing strings.

## Backend

- Specialty catalog carries `name_en` / `name_te` / `name_hi` (seeded, tested).
- AI disclaimers + emergency guidance are localized (te/en/hi) — tested in all three.
- AI intent keywords cover Telugu and Hindi scripts (e.g. `కంటి`, `గుండె నొప్పి`, `बच्चे को बुखार`).

## Mobile (Flutter)

- ARB files: `mobile/lib/l10n/app_te.arb` (primary), `app_en.arb`, `app_hi.arb`.
- `l10n.yaml` + `generate: true` run codegen (`flutter gen-l10n`).
- Locale resolution prefers the device language, falling back to **Telugu**.
- Fonts: Poppins (Latin), Noto Sans Telugu, Noto Sans Devanagari are declared in `pubspec.yaml`;
  **font files must be downloaded** (Google Fonts, SIL OFL) into `mobile/assets/fonts/` before
  building — they are not committed here. Until then Telugu/Devanagari render with platform fallback fonts.

## Admin

English-only for now (admin-facing); patient-facing localization lives in the mobile app. Adding
Telugu admin strings is a small follow-up using the same ARB approach.
