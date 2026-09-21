import "package:flutter/material.dart";
import "package:go_router/go_router.dart";

import "../../l10n/app_localizations.dart";
import "../../routing/app_router.dart";
import "../../theme/brand.dart";

/// Specialty detail (spec §9, §12): entry point into provider discovery for the
/// chosen specialty (e.g. Eye Care → eye-care doctors/hospitals). Services and
/// verified prices appear on provider profiles — nothing is fabricated here.
class SpecialtyPlaceholderScreen extends StatelessWidget {
  const SpecialtyPlaceholderScreen({required this.slug, super.key});

  final String slug;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(slug.replaceAll("-", " ").toUpperCase())),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.person_search_outlined, color: Brand.teal, size: 30),
              title: Text(l10n.doctors),
              subtitle: Text(l10n.providerPendingNote),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push("${AppRoutes.doctors}?specialty=$slug"),
            ),
          ),
          Card(
            child: ListTile(
              leading: const Icon(Icons.local_hospital_outlined, color: Brand.teal, size: 30),
              title: Text(l10n.hospitals),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push("${AppRoutes.hospitals}?specialty=$slug"),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            l10n.comingSoon,
            style: const TextStyle(fontSize: 13, color: Brand.darkText),
          ),
        ],
      ),
    );
  }
}
