import "package:flutter/material.dart";

import "../../l10n/app_localizations.dart";

/// Settings screen (spec §25: Settings, Privacy, Consent Management entries).
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.settings)),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.language),
            title: Text(l10n.language),
            subtitle: Text(l10n.telugu),
            onTap: () {
              // TODO(phase-1 polish): language switcher; backend stores
              // primary_language per user (see PATCH /api/v1/users/me).
            },
          ),
          ListTile(
            leading: const Icon(Icons.verified_user_outlined),
            title: Text(l10n.consentManagement),
            subtitle: Text(l10n.aiPlaceholderNote),
            onTap: () {
              // TODO(phase-5): consent management UI over GET/POST /api/v1/consents.
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(l10n.comingSoon)),
              );
            },
          ),
          ListTile(
            leading: const Icon(Icons.privacy_tip_outlined),
            title: Text(l10n.privacy),
            onTap: () {
              // TODO: privacy policy screen — content must come from the
              // backend/legal, never fabricated in-app.
            },
          ),
        ],
      ),
    );
  }
}
