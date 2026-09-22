import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Hospital discovery (spec §3, §11): live search over registered hospitals.
class HospitalSearchScreen extends ConsumerStatefulWidget {
  const HospitalSearchScreen({this.specialty, super.key});

  final String? specialty;

  @override
  ConsumerState<HospitalSearchScreen> createState() => _HospitalSearchScreenState();
}

class _HospitalSearchScreenState extends ConsumerState<HospitalSearchScreen> {
  List<dynamic>? _items;
  String? _error;
  String? _city;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>(
        "/api/v1/hospitals",
        query: {
          if (widget.specialty != null) "specialty": widget.specialty,
          if (_city != null && _city!.isNotEmpty) "city": _city,
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
      appBar: AppBar(title: Text(l10n.hospitals)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              decoration: InputDecoration(
                hintText: "City",
                prefixIcon: const Icon(Icons.location_city_outlined),
                suffixIcon: IconButton(icon: const Icon(Icons.search), onPressed: _load),
              ),
              onSubmitted: (value) {
                _city = value;
                _load();
              },
            ),
          ),
          Expanded(
            child: _error != null
                ? Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Text(l10n.offlineBanner),
                      OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
                    ]),
                  )
                : _items == null
                    ? const Center(child: CircularProgressIndicator())
                    : _items!.isEmpty
                        ? Center(child: Text(l10n.providerPendingNote))
                        : ListView.builder(
                            padding: const EdgeInsets.all(12),
                            itemCount: _items!.length,
                            itemBuilder: (context, index) {
                              final hosp = _items![index] as Map<String, dynamic>;
                              final verified = hosp["verification_status"] == "VERIFIED";
                              return Card(
                                child: ListTile(
                                  leading: const Icon(Icons.local_hospital_outlined, color: Brand.teal),
                                  title: Text(hosp["name"] as String? ?? ""),
                                  subtitle: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text("${hosp["hospital_type"]} · ${hosp["city"] ?? ""}"),
                                      Text(
                                        verified ? l10n.verified : l10n.notVerified,
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: verified ? Brand.teal : const Color(0xFFB45309),
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                      // Emergency is advertised only when verified (spec §14).
                                      if (hosp["emergency_verified"] == true)
                                        Text("🚨 ${l10n.emergencyAvailable}",
                                            style: const TextStyle(fontSize: 12)),
                                    ],
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
