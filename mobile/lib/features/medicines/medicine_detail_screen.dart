import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Medicine detail (Phase 4): identity fields, verified prices with full
/// provenance, and the transparent savings result (spec §9, §11, §12).
/// Savings are displayed ONLY when the engine returns CALCULATED —
/// INSUFFICIENT_DATA / NO_COMPARISON show an honest message instead.
class MedicineDetailScreen extends ConsumerStatefulWidget {
  const MedicineDetailScreen({required this.medicineId, super.key});

  final String medicineId;

  @override
  ConsumerState<MedicineDetailScreen> createState() => _MedicineDetailScreenState();
}

class _MedicineDetailScreenState extends ConsumerState<MedicineDetailScreen> {
  Map<String, dynamic>? _medicine;
  List<dynamic>? _prices;
  Map<String, dynamic>? _savings;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final med = await api.get<Map<String, dynamic>>("/api/v1/medicines/${widget.medicineId}");
      final prices = await api.get<List<dynamic>>("/api/v1/medicines/${widget.medicineId}/prices");
      final savings = await api.get<Map<String, dynamic>>("/api/v1/medicines/${widget.medicineId}/savings");
      setState(() {
        _medicine = med.data;
        _prices = prices.data ?? [];
        _savings = savings.data;
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
      appBar: AppBar(title: Text(l10n.medicineDetail)),
      body: _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(l10n.offlineBanner),
                  OutlinedButton(onPressed: _load, child: Text(l10n.retry)),
                ],
              ),
            )
          : _medicine == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text(_medicine!["name"] ?? "", style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 4),
                    Text(
                      "${l10n.strength}: ${_medicine!["strength"]} · "
                      "${l10n.dosageForm}: ${_medicine!["dosage_form"]} · "
                      "${l10n.packSize}: ${_medicine!["pack_size"]}",
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    if (_medicine!["prescription_required"] == true)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Chip(
                          avatar: const Icon(Icons.gavel, size: 18),
                          label: Text(l10n.prescriptionRequiredShort),
                          backgroundColor: BRAND.aiPurple.withValues(alpha: 0.12),
                        ),
                      ),
                    const Divider(height: 32),
                    Text(l10n.priceComparison, style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    if (_prices == null || _prices!.isEmpty)
                      Text(l10n.savingsInsufficient)
                    else
                      ..._prices!.map((p) {
                        final row = p as Map<String, dynamic>;
                        return Card(
                          child: ListTile(
                            title: Text("${row["pharmacy_name"] ?? ""} — ₹${row["price"]}"),
                            subtitle: Text(
                              "${l10n.priceSource}: ${row["source"]} · "
                              "${l10n.lastUpdated}: "
                              "${(row["last_updated"] ?? "").toString().split("T").first}",
                            ),
                            trailing: Chip(
                              label: Text(
                                row["verification_status"] ?? "",
                                style: const TextStyle(fontSize: 11),
                              ),
                            ),
                          ),
                        );
                      }),
                    const Divider(height: 32),
                    _savingsCard(l10n),
                  ],
                ),
    );
  }

  Widget _savingsCard(AppLocalizations l10n) {
    final s = _savings;
    if (s == null) return const SizedBox.shrink();
    final status = s["status"] as String?;
    if (status == "CALCULATED") {
      return Card(
        color: BRAND.teal.withValues(alpha: 0.08),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.potentialSavings, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                "₹${s["reference_price"]} → ₹${s["selected_price"]}   "
                "(₹${s["potential_savings"]})",
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(color: BRAND.teal),
              ),
              const SizedBox(height: 4),
              Text("${l10n.savingsReference}: ${s["reference_pharmacy_name"]} · "
                  "${l10n.savingsSelected}: ${s["selected_pharmacy_name"]}"),
              Text("${l10n.priceSource}: ${s["source"]} · "
                  "${l10n.lastUpdated}: ${(s["last_updated"] ?? "").toString().split("T").first}"),
            ],
          ),
        ),
      );
    }
    // Never fabricate a number when verified data is insufficient (spec §37).
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(l10n.savingsInsufficient),
      ),
    );
  }
}
