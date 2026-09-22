import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// My appointments (spec §10, §25): patient view with cancel (spec §9 rules).
class MyAppointmentsScreen extends ConsumerStatefulWidget {
  const MyAppointmentsScreen({super.key});

  @override
  ConsumerState<MyAppointmentsScreen> createState() => _MyAppointmentsScreenState();
}

class _MyAppointmentsScreenState extends ConsumerState<MyAppointmentsScreen> {
  List<dynamic>? _items;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>("/api/v1/appointments");
      setState(() {
        _items = resp.data ?? [];
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  Future<void> _cancel(String id) async {
    try {
      final api = ref.read(apiClientProvider);
      await api.post<dynamic>("/api/v1/appointments/$id/cancel");
      await _load();
    } catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Cancel failed — the appointment may already be confirmed.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.myAppointments)),
      body: _error != null
          ? Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(l10n.offlineBanner),
                OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
              ]),
            )
          : _items == null
              ? const Center(child: CircularProgressIndicator())
              : _items!.isEmpty
                  ? Center(child: Text(l10n.comingSoon))
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _items!.length,
                        itemBuilder: (context, index) {
                          final appt = _items![index] as Map<String, dynamic>;
                          final status = appt["status"] as String? ?? "";
                          final cancellable =
                              status == "REQUESTED" || status == "CONFIRMED" || status == "RESCHEDULED";
                          return Card(
                            child: ListTile(
                              title: Text("${appt["appointment_date"]} · ${appt["appointment_time"]}"),
                              subtitle: Text("${appt["specialty_slug"]} · $status"),
                              trailing: cancellable
                                  ? TextButton(
                                      onPressed: () => _cancel(appt["id"] as String),
                                      child: Text(l10n.cancelAppointment),
                                    )
                                  : null,
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
