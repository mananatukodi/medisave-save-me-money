import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Verified pharmacy discovery (Phase 4, spec §15). The backend only ever
/// returns VERIFIED+ACTIVE pharmacies here — the app shows exactly that.
class PharmacySearchScreen extends ConsumerStatefulWidget {
  const PharmacySearchScreen({super.key});

  @override
  ConsumerState<PharmacySearchScreen> createState() => _PharmacySearchScreenState();
}

class _PharmacySearchScreenState extends ConsumerState<PharmacySearchScreen> {
  List<dynamic>? _items;
  String? _error;
  String _city = "";

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>(
        "/api/v1/pharmacies",
        query: {
          "limit": 30,
          if (_city.isNotEmpty) "city": _city,
        },
      );
      setState(() {
        _items = resp.data ?? [];
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
      appBar: AppBar(title: Text(l10n.pharmacies)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              decoration: const InputDecoration(hintText: "City"),
              onSubmitted: (value) {
                _city = value;
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
                      final p = _items![index] as Map<String, dynamic>;
                      return ListTile(
                        leading: const Icon(Icons.local_pharmacy_outlined, color: BRAND.teal),
                        title: Text(p["name"] ?? ""),
                        subtitle: Text(
                          "${p["city"] ?? ""} · "
                          "${p["delivery_supported"] == true ? l10n.delivery : l10n.pickup}",
                        ),
                        trailing: Chip(
                          label: Text(
                            p["verification_status"] ?? "",
                            style: const TextStyle(fontSize: 11),
                          ),
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
