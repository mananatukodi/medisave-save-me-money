import "package:flutter/material.dart";

import "../../l10n/app_localizations.dart";
import "../../routing/app_router.dart";
import "../../theme/brand.dart";

/// Language selection (spec §25, §28) — Telugu first.
class LanguageScreen extends StatelessWidget {
  const LanguageScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 48),
              Text(
                l10n.appTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.w700,
                  color: Brand.teal,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                l10n.tagline,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 15, color: Brand.darkText),
              ),
              const SizedBox(height: 48),
              _LanguageTile(label: l10n.telugu, locale: const Locale("te"), route: AppRoutes.login),
              _LanguageTile(label: l10n.english, locale: const Locale("en"), route: AppRoutes.login),
              _LanguageTile(label: l10n.hindi, locale: const Locale("hi"), route: AppRoutes.login),
            ],
          ),
        ),
      ),
    );
  }
}

class _LanguageTile extends StatelessWidget {
  const _LanguageTile({required this.label, required this.locale, required this.route});

  final String label;
  final Locale locale;
  final String route;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: SizedBox(
        height: 64, // large touch target (spec §44)
        child: OutlinedButton(
          onPressed: () => Navigator.of(context).pushNamed(route),
          style: OutlinedButton.styleFrom(
            side: const BorderSide(color: Brand.teal, width: 1.5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
          child: Text(label, style: const TextStyle(fontSize: 18, color: Brand.darkText)),
        ),
      ),
    );
  }
}
