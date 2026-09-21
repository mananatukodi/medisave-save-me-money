import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Medicine discovery (Phase 4): search -> detail -> verified prices ->
/// savings -> order. All data comes from the real backend; empty states are
/// honest (spec §28, §37) — the app never shows invented medicines or prices.
class MedicineSearchScreen extends ConsumerStatefulWidget {
  const MedicineSearchScreen({super.key});

  @override
  ConsumerState<MedicineSearchScreen> createState() => _MedicineSearchScreenState();
}

class _MedicineSearchScreenState extends ConsumerState<MedicineSearchScreen> {
  List<dynamic>? _items;
  String? _error;
  String _query = "";

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>(
        "/api/v1/medicines",
        query: {"q": _query, "limit": 30},
      );
      setState(() {
        _items = resp.data ?? [];
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  String _stockLabel(String? status) {
    final l10n = AppLocalizations.of(context)!;
    switch (status) {
      case "IN_STOCK":
        return l10n.inStock;
      case "LOW_STOCK":
        return l10n.lowStock;
      case "OUT_OF_STOCK":
        return l10n.outOfStock;
      default:
        return l10n.stockUnknown; // UNKNOWN is never shown as available (spec §7)
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.medicinesSavings)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              decoration: InputDecoration(hintText: l10n.medicineSearch),
              onSubmitted: (value) {
                _query = value;
                _load();
              },
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  Text(l10n.offlineBanner, textAlign: TextAlign.center),
                  OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
                ],
              ),
            )
          else if (_items != null && _items!.isEmpty)
            Padding(
              padding: const EdgeInsets.all(24),
              child: Text(l10n.savingsInsufficient, textAlign: TextAlign.center),
            ),
          Expanded(
            child: _items == null
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    itemCount: _items!.length,
                    itemBuilder: (context, index) {
                      final m = _items![index] as Map<String, dynamic>;
                      return ListTile(
                        leading: Icon(
                          m["prescription_required"] == true
                              ? Icons.medication_liquid
                              : Icons.medication_outlined,
                          color: m["prescription_required"] == true ? BRAND.aiPurple : BRAND.teal,
                        ),
                        title: Text(m["name"] ?? ""),
                        subtitle: Text(
                          "${m["strength"]} · ${m["dosage_form"]} · ${m["pack_size"]}"
                          "${m["prescription_required"] == true ? " · Rx" : ""}",
                        ),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => context.push(
                          "/medicines/${m["id"]}",
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
