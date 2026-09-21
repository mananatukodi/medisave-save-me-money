import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Availability + booking (spec §8, §12): select slot → appointment → confirmation.
class BookingScreen extends ConsumerStatefulWidget {
  const BookingScreen({required this.doctorId, required this.serviceId, super.key});

  final String doctorId;
  final String serviceId;

  @override
  ConsumerState<BookingScreen> createState() => _BookingScreenState();
}

class _BookingScreenState extends ConsumerState<BookingScreen> {
  List<Map<String, dynamic>>? _days; // [{date, weekday, slots:[{time, available}]}]
  String? _selectedDate;
  String? _selectedTime;
  bool _busy = false;
  String? _error;
  String? _confirmedStatus;

  @override
  void initState() {
    super.initState();
    _loadAvailability();
  }

  Future<void> _loadAvailability() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>(
        "/api/v1/doctors/${widget.doctorId}/availability",
        query: {"days": 7},
      );
      setState(() {
        _days = (resp.data ?? [])
            .map((e) => e as Map<String, dynamic>)
            .where((day) => ((day["slots"] as List?) ?? []).isNotEmpty)
            .toList();
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  Future<void> _book() async {
    if (_selectedDate == null || _selectedTime == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.post<Map<String, dynamic>>(
        "/api/v1/appointments",
        body: {
          "doctor_id": widget.doctorId,
          "service_id": widget.serviceId,
          "appointment_date": _selectedDate,
          "appointment_time": _selectedTime,
        },
      );
      setState(() => _confirmedStatus = resp.data?["status"] as String? ?? "REQUESTED");
    } catch (_) {
      setState(() => _error = "Booking failed — the slot may have just been taken.");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    if (_confirmedStatus != null) {
      // Honest confirmation: REQUESTED until the provider confirms (spec §9, §54).
      return Scaffold(
        appBar: AppBar(title: Text(l10n.confirmBooking)),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.event_available_outlined, color: Brand.teal, size: 72),
                const SizedBox(height: 16),
                Text(l10n.appointmentRequested, textAlign: TextAlign.center),
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
                  child: Text(l10n.home),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(l10n.selectSlot)),
      body: _error != null
          ? Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(l10n.offlineBanner),
                OutlinedButton(onPressed: _loadAvailability, child: Text(l10n.retry)),
              ]),
            )
          : _days == null
              ? const Center(child: CircularProgressIndicator())
              : _days!.isEmpty
                  ? Center(child: Text(l10n.noSlots))
                  : Column(
                      children: [
                        SizedBox(
                          height: 56,
                          child: ListView.builder(
                            scrollDirection: Axis.horizontal,
                            padding: const EdgeInsets.all(8),
                            itemCount: _days!.length,
                            itemBuilder: (context, index) {
                              final day = _days![index];
                              final selected = _selectedDate == day["date"];
                              return Padding(
                                padding: const EdgeInsets.only(right: 8),
                                child: ChoiceChip(
                                  label: Text("${day["date"]}"),
                                  selected: selected,
                                  onSelected: (_) => setState(() {
                                    _selectedDate = day["date"] as String;
                                    _selectedTime = null;
                                  }),
                                ),
                              );
                            },
                          ),
                        ),
                        Expanded(
                          child: _selectedDate == null
                              ? Center(child: Text(l10n.selectSlot))
                              : Builder(builder: (context) {
                                  final day =
                                      _days!.firstWhere((d) => d["date"] == _selectedDate);
                                  final slots = (day["slots"] as List)
                                      .cast<Map<String, dynamic>>();
                                  if (slots.isEmpty) return Center(child: Text(l10n.noSlots));
                                  return GridView.count(
                                    crossAxisCount: 4,
                                    padding: const EdgeInsets.all(12),
                                    children: slots.map((slot) {
                                      final available = slot["available"] == true;
                                      final selected = _selectedTime == slot["time"];
                                      return Padding(
                                        padding: const EdgeInsets.all(4),
                                        child: OutlinedButton(
                                          onPressed: available
                                              ? () => setState(
                                                  () => _selectedTime = slot["time"] as String)
                                              : null,
                                          style: OutlinedButton.styleFrom(
                                            backgroundColor: selected
                                                ? Brand.teal
                                                : Colors.transparent,
                                            foregroundColor:
                                                selected ? Colors.white : Brand.darkText,
                                          ),
                                          child: Text(slot["time"] as String),
                                        ),
                                      );
                                    }).toList(),
                                  );
                                }),
                        ),
                        SafeArea(
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: SizedBox(
                              width: double.infinity,
                              child: FilledButton(
                                onPressed:
                                    _selectedTime == null && !_busy ? null : _book,
                                child: _busy
                                    ? const SizedBox(
                                        width: 20, height: 20,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2, color: Colors.white))
                                    : Text(l10n.confirmBooking),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
    );
  }
}
