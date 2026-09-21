import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Doctor profile (spec §12): profile → services → availability → booking.
class DoctorProfileScreen extends ConsumerStatefulWidget {
  const DoctorProfileScreen({required this.doctorId, super.key});

  final String doctorId;

  @override
  ConsumerState<DoctorProfileScreen> createState() => _DoctorProfileScreenState();
}

class _DoctorProfileScreenState extends ConsumerState<DoctorProfileScreen> {
  Map<String, dynamic>? _doctor;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<Map<String, dynamic>>("/api/v1/doctors/${widget.doctorId}");
      setState(() {
        _doctor = resp.data;
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final doctor = _doctor;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.doctorProfile)),
      body: _error != null
          ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(l10n.offlineBanner),
              OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
            ]))
          : doctor == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text(
                      doctor["full_name"] as String? ?? "",
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text("${doctor["specialty_slug"]} · ${doctor["qualifications"] ?? ""}"),
                    const SizedBox(height: 4),
                    Text(
                      doctor["verification_status"] == "VERIFIED"
                          ? "✅ ${l10n.verified}"
                          : "⏳ ${l10n.providerPendingNote}",
                      style: TextStyle(
                        color: doctor["verification_status"] == "VERIFIED"
                            ? Brand.teal
                            : const Color(0xFFB45309),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      "${doctor["years_experience"] ?? 0} ${l10n.experienceYears} · "
                      "${l10n.languagesSpoken}: ${doctor["languages"] ?? ""}",
                    ),
                    if ((doctor["about"] as String?)?.isNotEmpty == true)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(doctor["about"] as String),
                      ),
                    const SizedBox(height: 16),
                    Text(l10n.services,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                    ...((doctor["services"] as List?) ?? []).map((service) {
                      final s = service as Map<String, dynamic>;
                      final prices = (s["prices"] as List?) ?? [];
                      final price = prices.isNotEmpty ? prices.first as Map<String, dynamic> : null;
                      return Card(
                        child: ListTile(
                          title: Text(s["name_en"] as String? ?? ""),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text("${s["duration_minutes"]} ${l10n.minutes} · ${s["consultation_type"]}"),
                              if (price != null)
                                Text(
                                  price["verification_status"] == "VERIFIED"
                                      ? "₹${price["amount"]} (${l10n.priceVerified})"
                                      : "₹${price["amount"]} · ${l10n.priceNotVerified}",
                                  style: const TextStyle(fontSize: 12),
                                ),
                            ],
                          ),
                          trailing: FilledButton(
                            onPressed: doctor["verification_status"] == "VERIFIED"
                                ? () => context.push(
                                    "/book?doctorId=${widget.doctorId}&serviceId=${s["id"]}")
                                : null,
                            child: Text(l10n.bookAppointment),
                          ),
                        ),
                      );
                    }),
                  ],
                ),
    );
  }
}
