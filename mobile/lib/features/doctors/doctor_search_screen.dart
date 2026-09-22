import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Doctor discovery (spec §11, §12): Specialty → Provider list → Profile.
class DoctorSearchScreen extends ConsumerStatefulWidget {
  const DoctorSearchScreen({this.specialty, super.key});

  final String? specialty;

  @override
  ConsumerState<DoctorSearchScreen> createState() => _DoctorSearchScreenState();
}

class _DoctorSearchScreenState extends ConsumerState<DoctorSearchScreen> {
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
        "/api/v1/doctors",
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
      appBar: AppBar(title: Text(l10n.doctors)),
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
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  Text(l10n.offlineBanner, textAlign: TextAlign.center),
                  OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
                ],
              ),
            ),
          Expanded(
            child: _items == null
                ? const Center(child: CircularProgressIndicator())
                : _items!.isEmpty
                    ? Center(child: Text(l10n.providerPendingNote))
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _items!.length,
                        itemBuilder: (context, index) {
                          final doc = _items![index] as Map<String, dynamic>;
                          final verified = doc["verification_status"] == "VERIFIED";
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: Brand.teal.withOpacity(0.15),
                                child: const Icon(Icons.person_outlined, color: Brand.teal),
                              ),
                              title: Text(doc["full_name"] as String? ?? ""),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text("${doc["specialty_slug"]} · ${doc["city"] ?? ""}"),
                                  Text(
                                    verified ? l10n.verified : l10n.notVerified,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: verified ? Brand.teal : const Color(0xFFB45309),
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => context.push("/doctors/${doc["id"]}"),
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
