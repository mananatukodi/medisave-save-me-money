import "package:flutter/material.dart";
import "package:url_launcher/url_launcher.dart";

import "../../l10n/app_localizations.dart";
import "../../routing/app_router.dart";
import "../../theme/brand.dart";

/// Emergency home (Phase 7): one-tap SOS with confirmation, honest status
/// copy, and every critical action visible without menus.
///
/// HONESTY RULES (spec §12, §54 — carried from Phase 1, still binding):
/// - "Call requested" (device dialer) ≠ "call connected".
/// - "SOS event created on MediSaveAI server" ≠ "ambulance dispatched".
/// - Confirmation only ever comes from a real emergency provider.
class EmergencyHomeScreen extends StatelessWidget {
  const EmergencyHomeScreen({super.key});

  Future<void> _confirmAndRaise(BuildContext context, AppLocalizations l10n) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.sosConfirmTitle),
        content: Text(l10n.sosConfirmBody),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(l10n.cancel)),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFDC2626)),
            onPressed: () => Navigator.pop(context, true),
            child: Text(l10n.doSos),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    // The deterministic SOS endpoint never depends on AI. Offline behavior:
    // the action is queued client-side by the API client and the UI says
    // exactly what happened — nothing more.
    Navigator.of(context).pushNamed(AppRoutes.emergencyActive);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.emergencySos)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 8),
            const Icon(Icons.emergency_outlined, color: Color(0xFFDC2626), size: 88),
            const SizedBox(height: 20),
            SizedBox(
              height: 88, // large touch target (spec §44)
              child: FilledButton(
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFDC2626),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                ),
                onPressed: () => _confirmAndRaise(context, l10n),
                child: Text(l10n.doSos, style: const TextStyle(fontSize: 22)),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              l10n.sosConfirmBody,
              style: const TextStyle(fontSize: 13, color: Brand.darkText),
            ),
            const SizedBox(height: 24),
            SizedBox(
              height: 64,
              child: FilledButton.tonalIcon(
                icon: const Icon(Icons.call),
                label: Text(l10n.callEmergencyServices, style: const TextStyle(fontSize: 16)),
                onPressed: () => _call(context, l10n, "tel:108"),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              l10n.callRequestedNote,
              style: const TextStyle(fontSize: 11, color: Color(0xFF5A6478)),
            ),
            const SizedBox(height: 20),
            _Tile(
              icon: Icons.phone_in_talk_outlined,
              label: l10n.callEmergencyContact,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.emergencyContacts),
            ),
            _Tile(
              icon: Icons.local_hospital_outlined,
              label: l10n.nearbyEmergencyHospitals,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.emergencyHospitals),
            ),
            _Tile(
              icon: Icons.badge_outlined,
              label: l10n.emergencyProfileTitle,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.emergencyProfile),
            ),
            _Tile(
              icon: Icons.history,
              label: l10n.emergencyHistoryTitle,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.emergencyHistory),
            ),
          ],
        ),
      ),
    );
  }

  /// Opens the device dialer. The snackbar says the call was REQUESTED on
  /// the device — it can never claim the call connected.
  Future<void> _call(BuildContext context, AppLocalizations l10n, String url) async {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(l10n.callRequestedNote)),
    );
    try {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {
      // No dialer on this platform: the REQUESTED note above stays honest.
    }
  }
}

class _Tile extends StatelessWidget {
  const _Tile({required this.icon, required this.label, required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          leading: Icon(icon, color: Brand.teal, size: 28),
          title: Text(label, style: const TextStyle(fontSize: 15)),
          trailing: const Icon(Icons.chevron_right),
          onTap: onTap,
        ),
      );
}
