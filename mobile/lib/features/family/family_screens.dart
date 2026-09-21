import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Phase 6: Family Accounts & Caregiver Access.
///
/// SAFETY MODEL (must stay visible in the UI):
/// - A family relationship grants ZERO access by itself. The owner grants
///   explicit, scoped, time-bounded, revocable consent; the server enforces it
///   on every request.
/// - Invitation codes are shown exactly once and expire in 24 hours.
/// - The app never presents family access as automatic or implicit.

const _relationshipTypes = [
  "SPOUSE", "PARENT", "CHILD", "SIBLING", "GRANDPARENT", "GRANDCHILD", "CAREGIVER", "OTHER",
];

const _scopes = [
  "VIEW_HEALTH_RECORDS",
  "VIEW_APPOINTMENTS",
  "VIEW_MEDICINE_ORDERS",
  "REQUEST_APPOINTMENT",
  "REQUEST_REFILL",
  "RECEIVE_HEALTH_ALERTS",
];

const _statusColors = {
  "ACTIVE": Color(0xFF0B7A5C),
  "INVITED": Color(0xFF1D4ED8),
  "DECLINED": Color(0xFF92400E),
  "EXPIRED": Color(0xFF5A6478),
  "REVOKED": Color(0xFF991B1B),
};

/// Owner view: my family relationships, invitations, and consent grants.
class MyFamilyScreen extends ConsumerStatefulWidget {
  const MyFamilyScreen({super.key});

  @override
  ConsumerState<MyFamilyScreen> createState() => _MyFamilyScreenState();
}

class _MyFamilyScreenState extends ConsumerState<MyFamilyScreen> {
  List<dynamic>? _relationships;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiProvider);
      final resp = await api.get("/family/relationships");
      if (!mounted) return;
      setState(() {
        _relationships = resp.data as List<dynamic>;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  Future<void> _invite() async {
    final l10n = AppLocalizations.of(context)!;
    final nameController = TextEditingController();
    final emailController = TextEditingController();
    var relationshipType = _relationshipTypes.first;
    final saved = await showModalBottomSheet<Map<String, String>>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) => Padding(
          padding: EdgeInsets.only(
            left: 16, right: 16, top: 16,
            bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 16,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.inviteFamilyMember,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              TextField(
                controller: nameController,
                decoration: InputDecoration(labelText: l10n.displayNameField),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                value: relationshipType,
                decoration: InputDecoration(labelText: l10n.relationshipType),
                items: [
                  for (final t in _relationshipTypes)
                    DropdownMenuItem(value: t, child: Text(t)),
                ],
                onChanged: (v) => setSheetState(() => relationshipType = v ?? relationshipType),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: emailController,
                decoration: InputDecoration(labelText: l10n.invitedEmailField),
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.pop(sheetContext, {
                    "display_name": nameController.text.trim(),
                    "relationship_type": relationshipType,
                    "invited_email": emailController.text.trim(),
                  }),
                  child: Text(l10n.sendInvite),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (saved == null || (saved["display_name"] ?? "").isEmpty) return;
    try {
      final api = ref.read(apiProvider);
      final resp = await api.post("/family/invitations", data: saved);
      if (!mounted) return;
      final token = (resp.data as Map<String, dynamic>)["invitation_token"] as String?;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(l10n.sendInvite),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SelectableText(token ?? "", style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Text(l10n.invitationTokenNote,
                  style: const TextStyle(fontSize: 12, color: Color(0xFF5A6478))),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(l10n.acceptInvite)),
          ],
        ),
      );
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.familyLoadFailed)));
    }
  }

  Future<void> _grantConsent(String relationshipId) async {
    final l10n = AppLocalizations.of(context)!;
    final selected = <String>{};
    final saved = await showModalBottomSheet<bool>(
      context: context,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) => Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(l10n.grantConsent,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(l10n.familyConsentNote,
                  style: const TextStyle(fontSize: 12, color: Color(0xFF5A6478))),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final scope in _scopes)
                    FilterChip(
                      label: Text(scope),
                      selected: selected.contains(scope),
                      onSelected: (on) => setSheetState(() =>
                          on ? selected.add(scope) : selected.remove(scope)),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: selected.isEmpty ? null : () => Navigator.pop(sheetContext, true),
                  child: Text(l10n.grantConsent),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (saved != true || selected.isEmpty) return;
    try {
      final api = ref.read(apiProvider);
      await api.put("/family/relationships/$relationshipId/consent", data: {
        "scopes": selected.toList(),
        "purpose": "family care",
      });
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.familyLoadFailed)));
    }
  }

  Future<void> _post(String path, String relationshipId) async {
    final l10n = AppLocalizations.of(context)!;
    try {
      await ref.read(apiProvider).post("/family/relationships/$relationshipId/$path");
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.familyLoadFailed)));
    }
  }

  Future<void> _revokeConsent(String relationshipId) async {
    final l10n = AppLocalizations.of(context)!;
    try {
      await ref.read(apiProvider).delete("/family/relationships/$relationshipId/consent");
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.familyLoadFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final relationships = _relationships;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.myFamily)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              color: const Color(0xFFF1F4F9),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    const Icon(Icons.verified_user_outlined, color: Brand.teal),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(l10n.familyConsentNote,
                          style: const TextStyle(fontSize: 12, color: Color(0xFF3A4356))),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: _invite,
              icon: const Icon(Icons.person_add_alt_1),
              label: Text(l10n.inviteFamilyMember),
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Text(l10n.familyLoadFailed, style: TextStyle(color: BRAND.error)),
            if (relationships == null)
              const Center(child: Padding(
                padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
            if (relationships != null && relationships.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.familyNoRelationships,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Color(0xFF5A6478))),
              ),
            for (final rel in relationships ?? const [])
              _OwnerRelationshipCard(
                rel: rel as Map<String, dynamic>,
                onGrantConsent: () => _grantConsent(rel["id"] as String),
                onRevokeConsent: () => _revokeConsent(rel["id"] as String),
                onRemove: () => _post("revoke", rel["id"] as String),
              ),
          ],
        ),
      ),
    );
  }
}

class _OwnerRelationshipCard extends StatelessWidget {
  const _OwnerRelationshipCard({
    required this.rel,
    required this.onGrantConsent,
    required this.onRevokeConsent,
    required this.onRemove,
  });

  final Map<String, dynamic> rel;
  final VoidCallback onGrantConsent;
  final VoidCallback onRevokeConsent;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final status = rel["status"] as String? ?? "INVITED";
    final isActive = status == "ACTIVE";
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    "${rel["display_name"] ?? ""} · ${rel["relationship_type"] ?? ""}",
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: (_statusColors[status] ?? const Color(0xFF5A6478)).withOpacity(0.12),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    status,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: _statusColors[status] ?? const Color(0xFF5A6478),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (isActive)
                  FilledButton.tonal(
                    onPressed: onGrantConsent,
                    child: Text(l10n.grantConsent),
                  ),
                if (isActive)
                  OutlinedButton(onPressed: onRevokeConsent, child: Text(l10n.revokeConsent)),
                if (status == "ACTIVE" || status == "INVITED")
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(foregroundColor: const Color(0xFF991B1B)),
                    onPressed: onRemove,
                    child: Text(l10n.removeMember),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Member view: invitations addressed to me and access other people granted me.
class FamilyAccessScreen extends ConsumerStatefulWidget {
  const FamilyAccessScreen({super.key});

  @override
  ConsumerState<FamilyAccessScreen> createState() => _FamilyAccessScreenState();
}

class _FamilyAccessScreenState extends ConsumerState<FamilyAccessScreen> {
  List<dynamic>? _granted;
  List<dynamic>? _received;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiProvider);
      final granted = await api.get("/family/access-granted-to-me");
      final received = await api.get("/family/invitations/received");
      if (!mounted) return;
      setState(() {
        _granted = granted.data as List<dynamic>;
        _received = received.data as List<dynamic>;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  Future<void> _respond(String relationshipId, bool accept) async {
    final l10n = AppLocalizations.of(context)!;
    try {
      await ref.read(apiProvider)
          .post("/family/invitations/$relationshipId/${accept ? "accept" : "decline"}");
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.familyLoadFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.familyAccessTitle)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null)
              Text(l10n.familyLoadFailed, style: TextStyle(color: BRAND.error)),
            Text(l10n.invitationsReceived,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            if (_received != null && _received!.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(l10n.familyNoRelationships,
                    style: const TextStyle(fontSize: 12, color: Color(0xFF5A6478))),
              ),
            for (final inv in _received ?? const [])
              Card(
                child: ListTile(
                  title: Text(inv["display_name"] as String? ?? ""),
                  subtitle: Text(inv["relationship_type"] as String? ?? ""),
                  trailing: Wrap(
                    spacing: 6,
                    children: [
                      TextButton(
                        onPressed: () => _respond(inv["id"] as String, false),
                        child: Text(l10n.declineInvite),
                      ),
                      FilledButton(
                        onPressed: () => _respond(inv["id"] as String, true),
                        child: Text(l10n.acceptInvite),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 16),
            Text(l10n.accessGrantedToMe,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
            if (_granted != null && _granted!.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(l10n.familyNoRelationships,
                    style: const TextStyle(fontSize: 12, color: Color(0xFF5A6478))),
              ),
            for (final rel in _granted ?? const [])
              Card(
                child: ListTile(
                  title: Text(rel["display_name"] as String? ?? ""),
                  subtitle: Text(rel["relationship_type"] as String? ?? ""),
                  trailing: TextButton(
                    onPressed: () => _respond(rel["id"] as String, false),
                    child: Text(l10n.removeMember),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
