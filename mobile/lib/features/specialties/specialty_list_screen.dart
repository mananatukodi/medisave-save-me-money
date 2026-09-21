import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../routing/app_router.dart";
import "../../theme/brand.dart";

/// Specialty Care list (spec §6, §9): fetched live from the backend catalog.
class SpecialtyListScreen extends ConsumerStatefulWidget {
  const SpecialtyListScreen({super.key});

  @override
  ConsumerState<SpecialtyListScreen> createState() => _SpecialtyListScreenState();
}

class _Specialty {
  _Specialty({required this.slug, required this.emoji, required this.name});

  final String slug;
  final String emoji;
  final String name;
}

class _SpecialtyListScreenState extends ConsumerState<SpecialtyListScreen> {
  List<_Specialty>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>("/api/v1/specialties");
      final emojis = {
        "eye-care": "👁️", "dental-care": "🦷", "cardiology": "❤️", "pediatrics": "👶",
        "general-medicine": "🩺", "neurology": "🧠", "orthopedics": "🦴", "gynecology": "👩‍⚕️",
        "dermatology": "🧴", "ent": "👂", "pulmonology": "🫁", "nephrology": "🫘",
        "oncology": "🧬", "mental-health": "🧠", "physiotherapy": "🧑‍⚕️",
        "diagnostics-lab": "🧪", "other": "➕",
      };
      setState(() {
        _items = resp.data
                ?.map((e) => _Specialty(
                      slug: e["slug"] as String,
                      emoji: emojis[e["slug"]] ?? "🩺",
                      // Telugu-first name (spec §28)
                      name: (e["name_te"] as String?)?.isNotEmpty == true
                          ? e["name_te"] as String
                          : e["name_en"] as String,
                    ))
                .toList() ??
            [];
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.specialtyCare)),
      body: _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(l10n.offlineBanner, textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
                ],
              ),
            )
          : _items == null
              ? const Center(child: CircularProgressIndicator())
              : _items!.isEmpty
                  ? Center(child: Text(l10n.comingSoon))
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _items!.length,
                      itemBuilder: (context, index) => Card(
                        child: ListTile(
                          leading: Text(_items![index].emoji, style: const TextStyle(fontSize: 26)),
                          title: Text(_items![index].name),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => Navigator.of(context)
                              .pushNamed(AppRoutes.specialty(_items![index].slug)),
                        ),
                      ),
                    ),
    );
  }
}
