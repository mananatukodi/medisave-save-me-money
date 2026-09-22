import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:intl/intl.dart";
import "package:url_launcher/url_launcher.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Phase 7 emergency screens built on the deterministic (AI-free) emergency
/// API. Every screen states the truth: server status comes from the API,
/// availability is NOT_VERIFIED until a real provider confirms, and nothing
/// is ever fabricated.

const _sosRed = Color(0xFFDC2626);
const _muted = Color(0xFF5A6478);

Future<void> _dial(BuildContext context, AppLocalizations l10n, String url) async {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.callRequestedNote)));
  try {
    await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  } catch (_) {
    // No dialer available: the REQUESTED note above stays honest.
  }
}

/// Live SOS view after activation: status, call actions, cancel.
class SOSActiveScreen extends ConsumerStatefulWidget {
  const SOSActiveScreen({super.key});

  @override
  ConsumerState<SOSActiveScreen> createState() => _SOSActiveScreenState();
}

class _SOSActiveScreenState extends ConsumerState<SOSActiveScreen> {
  Map<String, dynamic>? _event;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadLatest();
  }

  Future<void> _loadLatest() async {
    try {
      final api = ref.read(apiProvider);
      final resp = await api.get("/emergency/history");
      final events = (resp.data as List<dynamic>).cast<Map<String, dynamic>>();
      final active = events.firstWhere(
        (e) =>
            e["status"] == "REQUESTED" ||
            e["status"] == "ALERTING" ||
            e["status"] == "CONTACTING" ||
            e["status"] == "ACTIVE",
        orElse: () => const {},
      );
      if (!mounted) return;
      setState(() {
        _event = active.isEmpty ? null : active;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  Future<void> _cancel(bool falseAlarm) async {
    final l10n = AppLocalizations.of(context)!;
    final event = _event;
    if (event == null) return;
    try {
      await ref.read(apiProvider).post("/emergency/sos/${event["id"]}/cancel", data: {
        "reason": falseAlarm ? "FALSE_ALARM" : "USER_CANCELLED",
      });
      if (!mounted) return;
      Navigator.of(context).popUntil((route) => route.isFirst);
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.emergencyLoadFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final event = _event;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.sosActiveTitle)),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _loadLatest,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Icon(
                event == null ? Icons.check_circle_outline : Icons.emergency_outlined,
                color: event == null ? Brand.teal : _sosRed,
                size: 72,
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  event == null ? l10n.sosNoneActive : l10n.sosActiveTitle,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  event == null ? l10n.sosCreatedOnServer : "${l10n.sosStatus}: ${event["status"]}",
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13, color: _muted),
                ),
              ),
              const SizedBox(height: 24),
              if (event != null) ...[
                SizedBox(
                  height: 64,
                  child: FilledButton.tonalIcon(
                    icon: const Icon(Icons.call),
                    label: Text(l10n.callEmergencyServices, style: const TextStyle(fontSize: 16)),
                    onPressed: () => _dial(context, l10n, "tel:108"),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  height: 56,
                  child: OutlinedButton(
                    onPressed: () => _cancel(false),
                    child: Text(l10n.sosCancelAction),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: 56,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(foregroundColor: _sosRed),
                    onPressed: () => _cancel(true),
                    child: Text(l10n.sosFalseAlarm),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              Text(
                l10n.sosCreatedOnServer,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 11, color: _muted),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Center(child: Text(l10n.emergencyLoadFailed,
                      style: TextStyle(color: BRAND.error))),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Patient emergency contacts: add / enable-disable / call.
class EmergencyContactsScreen extends ConsumerStatefulWidget {
  const EmergencyContactsScreen({super.key});

  @override
  ConsumerState<EmergencyContactsScreen> createState() => _EmergencyContactsScreenState();
}

class _EmergencyContactsScreenState extends ConsumerState<EmergencyContactsScreen> {
  List<dynamic>? _contacts;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ref.read(apiProvider).get("/emergency/contacts");
      if (!mounted) return;
      setState(() {
        _contacts = resp.data as List<dynamic>;
        _error = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = "load");
    }
  }

  Future<void> _add() async {
    final l10n = AppLocalizations.of(context)!;
    final name = TextEditingController();
    final phone = TextEditingController();
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => Padding(
        padding: EdgeInsets.only(
          left: 16, right: 16, top: 16,
          bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: name, decoration: InputDecoration(labelText: l10n.contactName)),
            const SizedBox(height: 8),
            TextField(
              controller: phone,
              keyboardType: TextInputType.phone,
              decoration: InputDecoration(labelText: l10n.contactPhone),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(sheetContext, true),
                child: Text(l10n.addContact),
              ),
            ),
          ],
        ),
      ),
    );
    if (saved != true || name.text.trim().isEmpty || phone.text.trim().isEmpty) return;
    try {
      await ref.read(apiProvider).post("/emergency/contacts", data: {
        "full_name": name.text.trim(),
        "phone_number": phone.text.trim(),
        "notification_preferences": "IN_APP",
      });
      await _load();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.emergencyLoadFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.emergencyContactsTitle)),
      floatingActionButton: FloatingActionButton(
        onPressed: _add,
        child: const Icon(Icons.person_add_alt_1),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) Text(l10n.emergencyLoadFailed, style: TextStyle(color: BRAND.error)),
            if (_contacts == null)
              const Center(child: Padding(
                padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
            if (_contacts != null && _contacts!.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.familyNoRelationships,
                    textAlign: TextAlign.center, style: const TextStyle(color: _muted)),
              ),
            for (final c in _contacts ?? const [])
              Card(
                child: ListTile(
                  leading: const Icon(Icons.person_outline, color: Brand.teal),
                  title: Text(c["full_name"] as String? ?? ""),
                  subtitle: Text(c["phone_number"] as String? ?? ""),
                  trailing: IconButton(
                    icon: const Icon(Icons.call, color: Brand.teal),
                    onPressed: () => _dial(context, l10n, "tel:${c["phone_number"]}"),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Patient-managed emergency profile. Every field is optional; the UI always
/// shows the user-provided disclaimer and the last-updated timestamp.
class EmergencyProfileScreen extends ConsumerStatefulWidget {
  const EmergencyProfileScreen({super.key});

  @override
  ConsumerState<EmergencyProfileScreen> createState() => _EmergencyProfileScreenState();
}

class _EmergencyProfileScreenState extends ConsumerState<EmergencyProfileScreen> {
  Map<String, dynamic>? _profile;
  final _bloodGroup = TextEditingController();
  final _allergies = TextEditingController();
  final _conditions = TextEditingController();
  final _medications = TextEditingController();
  final _notes = TextEditingController();
  String? _updatedAt;
  bool _dirty = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _bloodGroup.dispose();
    _allergies.dispose();
    _conditions.dispose();
    _medications.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final resp = await ref.read(apiProvider).get("/emergency/profile");
      final p = resp.data as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _profile = p;
        _updatedAt = p["updated_at"] as String?;
        _bloodGroup.text = (p["blood_group"] as String?) ?? "";
        _allergies.text = p["allergies"] as String? ?? "";
        _conditions.text = p["critical_conditions"] as String? ?? "";
        _medications.text = p["critical_medications"] as String? ?? "";
        _notes.text = p["emergency_notes"] as String? ?? "";
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _profile = {});
    }
  }

  Future<void> _save() async {
    final l10n = AppLocalizations.of(context)!;
    try {
      await ref.read(apiProvider).put("/emergency/profile", data: {
        "blood_group": _bloodGroup.text.trim().isEmpty ? null : _bloodGroup.text.trim(),
        "allergies": _allergies.text,
        "critical_conditions": _conditions.text,
        "critical_medications": _medications.text,
        "emergency_notes": _notes.text,
      });
      await _load();
      if (!mounted) return;
      setState(() => _dirty = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.save)));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(l10n.emergencyLoadFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final updatedAt = _updatedAt != null
        ? DateFormat.yMMMd().add_Hm().format(DateTime.tryParse(_updatedAt!)?.toLocal() ?? DateTime.now())
        : "—";
    return Scaffold(
      appBar: AppBar(title: Text(l10n.emergencyProfileTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text("${l10n.lastUpdated}: $updatedAt",
              style: const TextStyle(fontSize: 12, color: _muted)),
          const SizedBox(height: 12),
          Card(
            color: const Color(0xFFF1F4F9),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(l10n.profileDisclaimer,
                  style: const TextStyle(fontSize: 12, color: Color(0xFF3A4356))),
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _bloodGroup,
            onChanged: (_) => _dirty = true,
            decoration: InputDecoration(labelText: l10n.bloodGroup),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _allergies,
            onChanged: (_) => _dirty = true,
            maxLines: 2,
            decoration: InputDecoration(labelText: l10n.allergies),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _conditions,
            onChanged: (_) => _dirty = true,
            maxLines: 2,
            decoration: InputDecoration(labelText: l10n.criticalConditions),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _medications,
            onChanged: (_) => _dirty = true,
            maxLines: 2,
            decoration: InputDecoration(labelText: l10n.criticalMedications),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _notes,
            onChanged: (_) => _dirty = true,
            maxLines: 3,
            decoration: InputDecoration(labelText: l10n.emergencyNotes),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: 52,
            child: FilledButton.icon(
              onPressed: _save,
              icon: const Icon(Icons.save_outlined),
              label: Text(l10n.save),
            ),
          ),
        ],
      ),
    );
  }
}

/// Verified emergency-capable hospitals nearby. Availability is honestly
/// NOT_VERIFIED — the app never invents beds, ICU counts, doctors, or ETAs.
class NearbyEmergencyHospitalsScreen extends ConsumerStatefulWidget {
  const NearbyEmergencyHospitalsScreen({super.key});

  @override
  ConsumerState<NearbyEmergencyHospitalsScreen> createState() =>
      _NearbyEmergencyHospitalsScreenState();
}

class _NearbyEmergencyHospitalsScreenState
    extends ConsumerState<NearbyEmergencyHospitalsScreen> {
  List<dynamic>? _hospitals;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      // Location: Phase 7 uses a fixed demo origin until the device location
      // integration is configured; the API treats location as optional.
      final resp = await ref.read(apiProvider)
          .get("/emergency/hospitals/nearby", query: {"lat": "17.3850", "lng": "78.4867"});
      if (!mounted) return;
      setState(() {
        _hospitals = resp.data as List<dynamic>;
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
    return Scaffold(
      appBar: AppBar(title: Text(l10n.nearbyEmergencyHospitals)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) Text(l10n.emergencyLoadFailed, style: TextStyle(color: BRAND.error)),
            if (_hospitals == null)
              const Center(child: Padding(
                padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
            if (_hospitals != null && _hospitals!.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.emergencyLoadFailed,
                    textAlign: TextAlign.center, style: const TextStyle(color: _muted)),
              ),
            for (final h in _hospitals ?? const [])
              Card(
                child: ListTile(
                  title: Text(h["name"] as String? ?? ""),
                  subtitle: Text(
                    "${h["city"] ?? ""} · ${(h["distance_km"] ?? 0).toString()} km\n"
                    "${l10n.availabilityNotVerified}",
                  ),
                  isThreeLine: true,
                  trailing: Icon(
                    h["emergency_verified"] == true ? Icons.verified_outlined : Icons.info_outline,
                    color: h["emergency_verified"] == true ? Brand.teal : _muted,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Emergency history: honest terminal states, never deleted.
class EmergencyHistoryScreen extends ConsumerStatefulWidget {
  const EmergencyHistoryScreen({super.key});

  @override
  ConsumerState<EmergencyHistoryScreen> createState() => _EmergencyHistoryScreenState();
}

class _EmergencyHistoryScreenState extends ConsumerState<EmergencyHistoryScreen> {
  List<dynamic>? _events;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ref.read(apiProvider).get("/emergency/history");
      if (!mounted) return;
      setState(() {
        _events = resp.data as List<dynamic>;
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
    return Scaffold(
      appBar: AppBar(title: Text(l10n.emergencyHistoryTitle)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_error != null) Text(l10n.emergencyLoadFailed, style: TextStyle(color: BRAND.error)),
            if (_events == null)
              const Center(child: Padding(
                padding: EdgeInsets.all(32), child: CircularProgressIndicator())),
            for (final e in _events ?? const [])
              Card(
                child: ListTile(
                  leading: Icon(
                    e["status"] == "RESOLVED" || e["status"] == "CANCELLED"
                        ? Icons.check_circle_outline
                        : Icons.emergency_outlined,
                    color: e["status"] == "RESOLVED" || e["status"] == "CANCELLED"
                        ? Brand.teal
                        : _sosRed,
                  ),
                  title: Text("${e["emergency_type"] ?? "MEDICAL"} · ${e["status"]}"),
                  subtitle: Text(e["created_at"] as String? ?? ""),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Hospital handoff status view. Acceptance requires the real hospital to
/// confirm — the app never shows HANDOFF_ACCEPTED without the API saying so.
class EmergencyHandoffScreen extends ConsumerStatefulWidget {
  const EmergencyHandoffScreen({super.key, required this.eventId});

  final String eventId;

  @override
  ConsumerState<EmergencyHandoffScreen> createState() => _EmergencyHandoffScreenState();
}

class _EmergencyHandoffScreenState extends ConsumerState<EmergencyHandoffScreen> {
  List<dynamic>? _handoffs;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final resp = await ref.read(apiProvider).get("/emergency/${widget.eventId}/handoffs");
      if (!mounted) return;
      setState(() {
        _handoffs = resp.data as List<dynamic>;
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
    return Scaffold(
      appBar: AppBar(title: Text(l10n.handoffTitle)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(l10n.handoffRequestedNote,
                style: const TextStyle(fontSize: 12, color: _muted)),
            const SizedBox(height: 12),
            if (_error != null) Text(l10n.emergencyLoadFailed, style: TextStyle(color: BRAND.error)),
            if (_handoffs != null && _handoffs!.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(l10n.emergencyLoadFailed,
                    textAlign: TextAlign.center, style: const TextStyle(color: _muted)),
              ),
            for (final h in _handoffs ?? const [])
              Card(
                child: ListTile(
                  title: Text(h["status"] as String? ?? ""),
                  subtitle: Text(h["requested_at"] as String? ?? ""),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
