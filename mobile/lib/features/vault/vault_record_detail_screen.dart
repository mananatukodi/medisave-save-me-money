import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:intl/intl.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Record detail (Phase 5): metadata, signed-URL download, share management,
/// and the per-record access history. Shares are scope-bound and revocable;
/// every sensitive action is audited server-side (spec §7, §8, §9).
class VaultRecordDetailScreen extends ConsumerStatefulWidget {
  const VaultRecordDetailScreen({super.key, required this.recordId});

  final String recordId;

  @override
  ConsumerState<VaultRecordDetailScreen> createState() =>
      _VaultRecordDetailScreenState();
}

class _VaultRecordDetailScreenState
    extends ConsumerState<VaultRecordDetailScreen> {
  Map<String, dynamic>? _record;
  List<dynamic>? _shares;
  List<dynamic>? _audit;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = ref.read(apiProvider);
    try {
      final rec = await api.get("/health-records/${widget.recordId}");
      final shares = await api.get("/health-records/shares");
      final audit = await api.get("/health-records/${widget.recordId}/audit");
      if (!mounted) return;
      setState(() {
        _record = rec.data as Map<String, dynamic>;
        _shares = (shares.data as List<dynamic>)
            .where((s) => s["record_id"] == widget.recordId)
            .toList();
        _audit = audit.data as List<dynamic>;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  Future<void> _download() async {
    final api = ref.read(apiProvider);
    try {
      final resp = await api
          .get("/health-records/${widget.recordId}/download-url");
      final url = (resp.data as Map<String, dynamic>)["url"] as String?;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(url == null
            ? AppLocalizations.of(context)!.accessDenied
            : AppLocalizations.of(context)!.download),
      ));
      // A real client would open the short-lived signed URL here.
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppLocalizations.of(context)!.permissionRequired),
      ));
    }
  }

  Future<void> _share() async {
    final api = ref.read(apiProvider);
    final grantee = TextEditingController();
    final purpose = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppLocalizations.of(ctx)!.shareRecord),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: grantee,
              decoration: const InputDecoration(labelText: "Grantee user ID"),
            ),
            TextField(
              controller: purpose,
              decoration:
                  const InputDecoration(labelText: "Purpose"),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text("Cancel")),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(AppLocalizations.of(ctx)!.shareRecord)),
        ],
      ),
    );
    if (ok != true || grantee.text.trim().isEmpty) return;
    try {
      await api.post("/health-records/shares", data: {
        "record_id": widget.recordId,
        "grantee_user_id": grantee.text.trim(),
        "grantee_type": "DOCTOR",
        "scope": "VIEW_RECORD",
        "purpose": purpose.text.trim().isEmpty ? "consultation" : purpose.text.trim(),
        "expires_in_days": 7,
      });
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppLocalizations.of(context)!.permissionRequired),
      ));
    }
  }

  Future<void> _revoke(String shareId) async {
    final api = ref.read(apiProvider);
    try {
      await api.delete("/health-records/shares/$shareId");
      await _load();
    } catch (_) {
      // keep UI consistent; server is authoritative
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final rec = _record;
    return Scaffold(
      appBar: AppBar(title: Text(rec?["title"] as String? ?? l10n.healthVault)),
      body: _error != null || rec == null
          ? Center(child: Text(l10n.uploadFailed))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text("${rec["category"] ?? ""} · ${rec["status"] ?? ""}",
                            style: TextStyle(color: BRAND.teal, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 8),
                        Text("${l10n.recordDate}: ${rec["record_date"] ?? "—"}"),
                        if (rec["description"] != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(rec["description"] as String),
                          ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          children: [
                            OutlinedButton(
                                onPressed: _download, child: Text(l10n.download)),
                            FilledButton(
                                onPressed: _share, child: Text(l10n.shareRecord)),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(l10n.sharedAccess,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                if ((_shares ?? const []).isEmpty)
                  Text(l10n.vaultEmpty,
                      style: const TextStyle(color: Color(0xFF8A93A6))),
                for (final share in _shares ?? const [])
                  ListTile(
                    leading: const Icon(Icons.share),
                    title: Text(share["scope"] as String? ?? ""),
                    subtitle: Text(
                        "${share["grantee_type"] ?? ""} · expires ${share["expires_at"] ?? "—"}"),
                    trailing: share["revoked_at"] == null
                        ? TextButton(
                            onPressed: () => _revoke(share["id"] as String),
                            child: Text(l10n.revokeAccess),
                          )
                        : Text(l10n.revokeAccess,
                            style: const TextStyle(color: Color(0xFF8A93A6))),
                  ),
                const SizedBox(height: 16),
                Text(l10n.accessHistory,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                for (final ev in _audit ?? const [])
                  ListTile(
                    dense: true,
                    leading: Icon(
                      ev["result"] == "DENIED" ? Icons.block : Icons.check_circle,
                      color: ev["result"] == "DENIED" ? BRAND.error : BRAND.teal,
                      size: 20,
                    ),
                    title: Text(ev["action"] as String? ?? ""),
                    subtitle: Text(ev["created_at"] as String? ?? ""),
                  ),
              ],
            ),
    );
  }
}
