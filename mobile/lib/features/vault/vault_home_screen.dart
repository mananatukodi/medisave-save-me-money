import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";
import "package:intl/intl.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Health Vault home (Phase 5): category sections over the patient's records.
/// Patient-owned, consent-controlled access; the app never fabricates records
/// and never exposes storage paths (spec §12, §15).
class VaultHomeScreen extends ConsumerStatefulWidget {
  const VaultHomeScreen({super.key});

  @override
  ConsumerState<VaultHomeScreen> createState() => _VaultHomeScreenState();
}

class _VaultHomeScreenState extends ConsumerState<VaultHomeScreen> {
  List<dynamic>? _records;
  String? _error;
  String _category = "";

  static const _categories = [
    ("PRESCRIPTION", "prescriptions"),
    ("LAB_REPORT", "labReports"),
    ("DIAGNOSTIC_REPORT", "diagnosticReports"),
    ("IMAGING_REPORT", "medicalRecords"),
    ("HOSPITAL_RECORD", "medicalRecords"),
    ("INSURANCE_DOCUMENT", "medicalRecords"),
    ("OTHER", "medicalRecords"),
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiProvider);
      final resp = await api.get("/health-records");
      if (!mounted) return;
      setState(() {
        _records = resp.data as List<dynamic>;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final records = _records;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.healthVault)),
      body: RefreshIndicator(
        onRefresh: () async => _load(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: Text(l10n.vaultAllCategories),
                  selected: _category.isEmpty,
                  onSelected: (_) => setState(() => _category = ""),
                ),
                for (final (code, key) in _categories)
                  ChoiceChip(
                    label: Text(_categoryLabel(l10n, code, key)),
                    selected: _category == code,
                    onSelected: (_) => setState(() => _category = code),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(l10n.uploadFailed, style: TextStyle(color: BRAND.error)),
            if (records == null)
              const Center(child: Padding(
                padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
            if (records != null && records.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.vaultEmpty,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Color(0xFF5A6478))),
              ),
            for (final rec in records ?? const [])
              if (_category.isEmpty || rec["category"] == _category)
                Card(
                  child: ListTile(
                    title: Text(rec["title"] as String? ?? ""),
                    subtitle: Text(
                      "${_categoryLabel(l10n, rec["category"] as String? ?? "OTHER", "medicalRecords")}"
                      " · ${rec["record_date"] ?? ""}",
                    ),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push("/vault/${rec["id"]}"),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  String _categoryLabel(AppLocalizations l10n, String code, String key) {
    switch (key) {
      case "prescriptions":
        return l10n.prescriptions;
      case "labReports":
        return l10n.labReports;
      case "diagnosticReports":
        return l10n.diagnosticReports;
      default:
        return l10n.medicalRecords;
    }
  }
}
