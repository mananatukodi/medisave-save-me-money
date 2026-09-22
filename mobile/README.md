# MediSave AI — Mobile (Flutter)

Patient-first Flutter app: Riverpod + GoRouter + Dio, Telugu-first localization (te/en/hi).

## Status: AUTHORED — BUILD REQUIRES FLUTTER SDK

The Flutter SDK was **not available** on the machine where this code was written, so the app is
**authored but not compiled** (per spec §54 we do not claim an untested build works).

## To build

1. Install Flutter (stable channel).
2. Add font files (see `pubspec.yaml`): Poppins, Noto Sans Telugu, Noto Sans Devanagari under
   `assets/fonts/` (SIL OFL licensed, from Google Fonts).
3. Run:

```bash
flutter pub get
flutter gen-l10n
flutter run --dart-define=MEDISAVE_API_BASE_URL=http://10.0.2.2:8000
```

## Screens implemented (spec §25)

- Language selection (Telugu first) → Login → Home
- Home dashboard with all spec §26 modules (AI assistant, SOS, discovery, specialty chips,
  my appointments, records, insurance, labs, family, support)
- AI Health Assistant chat (renders backend structured responses + navigation actions)
- Emergency SOS (honest REQUESTED-status copy; no fabricated dispatch)
- Specialty Care list (live) → specialty detail → filtered doctor/hospital discovery
- **Phase 3:** Doctor Search (specialty/city filters, verified badges) · Doctor Profile (services,
  price-provenance labels) · Hospital Search · Booking (slot grid, honest REQUESTED confirmation) ·
  My Appointments (cancel per state-machine rules)
- Settings (language / consent / privacy entries)

## Screens intentionally NOT implemented yet

Hospital profile detail, medicines/savings, records, insurance, payments, family, notifications,
support detail — see `docs/MEDISAVE_AI_IMPLEMENTATION_PLAN.md` for the honest phase map.
Placeholder screens say "Coming soon" and never fake data. Provider profiles only ever display
backend verification status; unverified providers cannot be booked (server-enforced).
