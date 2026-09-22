import "package:flutter/material.dart";
import "package:go_router/go_router.dart";

import "../../l10n/app_localizations.dart";
import "../../routing/app_router.dart";
import "../../theme/brand.dart";

/// Home dashboard (spec §26): AI assistant, SOS, discovery, specialties,
/// records, insurance, support — every mandatory module surfaced.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        actions: [
          IconButton(
            tooltip: l10n.settings,
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).pushNamed(AppRoutes.settings),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _AiAssistantCard(l10n: l10n),
            const SizedBox(height: 12),
            _SosCard(l10n: l10n),
            const SizedBox(height: 12),
            _SectionTitle(l10n.findDoctor),
            _Tile(
              icon: Icons.person_search_outlined,
              label: l10n.findDoctor,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.doctors),
            ),
            _Tile(
              icon: Icons.local_hospital_outlined,
              label: l10n.findHospital,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.hospitals),
            ),
            const SizedBox(height: 12),
            _SectionTitle(l10n.specialtyCare),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _SpecialtyChip(
                  emoji: "👁️", label: l10n.eyeCare,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("eye-care")),
                ),
                _SpecialtyChip(
                  emoji: "🦷", label: l10n.dentalCare,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("dental-care")),
                ),
                _SpecialtyChip(
                  emoji: "❤️", label: l10n.cardiology,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("cardiology")),
                ),
                _SpecialtyChip(
                  emoji: "👶", label: l10n.pediatrics,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("pediatrics")),
                ),
                _SpecialtyChip(
                  emoji: "🦴", label: l10n.orthopedics,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("orthopedics")),
                ),
                _SpecialtyChip(
                  emoji: "🧴", label: l10n.dermatology,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("dermatology")),
                ),
                _SpecialtyChip(
                  emoji: "👂", label: l10n.ent,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialty("ent")),
                ),
                _SpecialtyChip(
                  emoji: "➕", label: l10n.viewAllSpecialties,
                  onTap: () => Navigator.of(context).pushNamed(AppRoutes.specialties),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _SectionTitle(l10n.medicinesSavings),
            _Tile(
              icon: Icons.event_note_outlined,
              label: l10n.myAppointments,
              onTap: () => Navigator.of(context).pushNamed(AppRoutes.myAppointments),
            ),
            _Tile(
              icon: Icons.medication_outlined,
              label: l10n.medicinesSavings,
              onTap: () => context.push(AppRoutes.medicines),
            ),
            _Tile(
              icon: Icons.folder_shared_outlined,
              label: l10n.healthRecords,
              onTap: () => context.push(AppRoutes.vault),
            ),
            _Tile(
              icon: Icons.shield_outlined,
              label: l10n.insuranceClaims,
              onTap: () => _comingSoon(context, l10n),
            ),
            _Tile(
              icon: Icons.science_outlined,
              label: l10n.labTests,
              onTap: () => _comingSoon(context, l10n),
            ),
            _Tile(
              icon: Icons.family_restroom_outlined,
              label: l10n.familyHealth,
              onTap: () => context.push(AppRoutes.family),
            ),
            _Tile(
              icon: Icons.diversity_1_outlined,
              label: l10n.familyAccessTitle,
              onTap: () => context.push(AppRoutes.familyAccess),
            ),
            _Tile(
              icon: Icons.support_agent_outlined,
              label: l10n.support,
              onTap: () => _comingSoon(context, l10n),
            ),
          ],
        ),
      ),
    );
  }

  void _comingSoon(BuildContext context, AppLocalizations l10n) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("${l10n.comingSoon} — see docs/MEDISAVE_AI_IMPLEMENTATION_PLAN.md")),
    );
  }
}

class _AiAssistantCard extends StatelessWidget {
  const _AiAssistantCard({required this.l10n});
  final AppLocalizations l10n;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Brand.aiPurple,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.ai),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "🤖 ${l10n.aiAssistant}",
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                l10n.aiPlaceholderNote,
                style: TextStyle(color: Colors.white.withOpacity(0.9), fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SosCard extends StatelessWidget {
  const _SosCard({required this.l10n});
  final AppLocalizations l10n;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFFDC2626),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.emergency),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.emergency_outlined, color: Colors.white, size: 32),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  l10n.emergencySos,
                  style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
                ),
              ),
              const Icon(Icons.chevron_right, color: Colors.white),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 8),
        child: Text(text,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Brand.darkText)),
      );
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

class _SpecialtyChip extends StatelessWidget {
  const _SpecialtyChip({required this.emoji, required this.label, required this.onTap});
  final String emoji;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          width: 104,
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFE3E8F0)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(emoji, style: const TextStyle(fontSize: 26)),
              const SizedBox(height: 4),
              Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 12)),
            ],
          ),
        ),
      );
}
