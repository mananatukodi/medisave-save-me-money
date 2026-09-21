# MediSave AI — Offline Mode

Goal (spec §29): never silently lose user data; clear offline state; queued actions.

## Implemented (mobile foundation)

- `ApiClient.enqueueForRetry(path, body)` queues failed POSTs in memory.
- `flushQueue()` retries all queued actions on reconnect; failed items stay queued (never dropped).
- Specialty list shows an explicit offline state with a Retry button.
- Localized offline banner string in all three ARB files.

## Not yet implemented (honest gaps)

- Persistent queue across app restarts (currently in-memory) — planned with `shared_preferences`/secure storage in the records phase.
- Connectivity detection package + global offline banner widget.
- Cached record metadata (Phase 5), background sync worker, sync status UI.

## Backend

APIs are paginated-capable and lightweight; compression is deferred to the reverse proxy layer
(see DEPLOYMENT.md). No long-running client polling; notifications (Phase 8) will use push.
