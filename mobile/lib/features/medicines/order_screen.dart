import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:go_router/go_router.dart";

import "../../core/network/api_provider.dart";
import "../../l10n/app_localizations.dart";
import "../../theme/brand.dart";

/// Order placement (Phase 4): pickup/delivery-capable verified pharmacies
/// only; Rx-required medicines show the honest gating message. No payment is
/// taken — order starts at CREATED / PRESCRIPTION_REQUIRED (spec §14, §18).
class OrderScreen extends ConsumerStatefulWidget {
  const OrderScreen({required this.medicineId, super.key});

  final String medicineId;

  @override
  ConsumerState<OrderScreen> createState() => _OrderScreenState();
}

class _OrderScreenState extends ConsumerState<OrderScreen> {
  List<dynamic>? _pharmacies;
  bool _pickup = true;
  bool _placing = false;
  String? _message;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>(
        "/api/v1/pharmacies",
        query: {"medicine_id": widget.medicineId},
      );
      setState(() {
        _pharmacies = resp.data ?? [];
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  Future<void> _place(String pharmacyId) async {
    final loc = AppLocalizations.of(context)!; // captured before async work
    setState(() {
      _placing = true;
      _message = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.post<Map<String, dynamic>>(
        "/api/v1/orders",
        body: {
          "pharmacy_id": pharmacyId,
          "items": [{"medicine_id": widget.medicineId, "quantity": 1}],
          "pickup_option": _pickup,
        },
      );
      final status = resp.data?["status"] as String?;
      if (!mounted) return;
      setState(() {
        _placing = false;
        _message = status == "PRESCRIPTION_REQUIRED"
            ? loc.prescriptionRequiredShort
            : loc.orderPlaced;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _placing = false;
        _message = loc.offlineBanner;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(loc.placeOrder)),
      body: Column(
        children: [
          RadioListTile<bool>(
            value: true,
            groupValue: _pickup,
            onChanged: (v) => setState(() => _pickup = v ?? true),
            title: Text(loc.pickup),
          ),
          RadioListTile<bool>(
            value: false,
            groupValue: _pickup,
            onChanged: (v) => setState(() => _pickup = !(v ?? true)),
            title: Text(loc.delivery),
          ),
          if (_error != null) Padding(padding: const EdgeInsets.all(12), child: Text(loc.offlineBanner)),
          if (_message != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_message!, style: const TextStyle(color: BRAND.teal)),
            ),
          Expanded(
            child: _pharmacies == null
                ? const Center(child: CircularProgressIndicator())
                : _pharmacies!.isEmpty
                    ? Center(child: Text(loc.savingsInsufficient))
                    : ListView.builder(
                        itemCount: _pharmacies!.length,
                        itemBuilder: (context, index) {
                          final p = _pharmacies![index] as Map<String, dynamic>;
                          return ListTile(
                            title: Text(p["name"] ?? ""),
                            subtitle: Text(
                              "${p["city"] ?? ""} · "
                              "${p["delivery_supported"] == true ? loc.delivery : loc.pickup}",
                            ),
                            trailing: _placing
                                ? const SizedBox(
                                    width: 20, height: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2),
                                  )
                                : FilledButton(
                                    onPressed: () => _place(p["id"] as String),
                                    child: Text(loc.placeOrder),
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

/// Patient medicine history: own orders only (spec §20), with honest status.
class MyOrdersScreen extends ConsumerStatefulWidget {
  const MyOrdersScreen({super.key});

  @override
  ConsumerState<MyOrdersScreen> createState() => _MyOrdersScreenState();
}

class _MyOrdersScreenState extends ConsumerState<MyOrdersScreen> {
  List<dynamic>? _orders;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final api = ref.read(apiClientProvider);
      final resp = await api.get<List<dynamic>>("/api/v1/orders");
      setState(() {
        _orders = resp.data ?? [];
        _error = null;
      });
    } catch (_) {
      setState(() => _error = "offline");
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(loc.myOrders)),
      body: _error != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(loc.offlineBanner),
                  OutlinedButton(onPressed: _load, child: Text(loc.retry)),
                ],
              ),
            )
          : _orders == null
              ? const Center(child: CircularProgressIndicator())
              : _orders!.isEmpty
                  ? Center(child: Text(loc.comingSoon))
                  : ListView.builder(
                      itemCount: _orders!.length,
                      itemBuilder: (context, index) {
                        final o = _orders![index] as Map<String, dynamic>;
                        final items = (o["items"] as List?) ?? [];
                        return ListTile(
                          leading: const Icon(Icons.receipt_long_outlined),
                          title: Text(
                            items.map((i) => (i as Map<String, dynamic>)["medicine_name"]).join(", "),
                          ),
                          subtitle: Text(
                            "${loc.orderStatus}: ${o["status"]} · "
                            "${o["currency"]} ${o["total"]}",
                          ),
                          isThreeLine: false,
                        );
                      },
                    ),
    );
  }
}
