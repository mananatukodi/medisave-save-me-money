# MediSave AI — Medicines & Savings Engine (Phase 4)

*"Save Me Money" — but every claimed saving must be supported by actual
verified data.*

## 1. Data model

| Table | Purpose |
|---|---|
| `medicines` | Canonical medicine entity (name, generic, brand, manufacturer, strength, `dosage_form`, `pack_size`, `prescription_required`, `data_source` provenance). |
| `medicine_aliases` | Search aliases (brand/regional spellings). |
| `pharmacies` | Registered pharmacy with `verification_status` aggregate. |
| `pharmacy_verifications` | Immutable history of every SUPER_ADMIN decision. |
| `pharmacy_inventory` | One row per (pharmacy, medicine): `IN_STOCK | LOW_STOCK | OUT_OF_STOCK | UNKNOWN`. |
| `medicine_prices` | Versioned price rows with full provenance. |
| `medicine_price_history` | Append-only event log (`SUBMITTED | VERIFIED | REJECTED | EXPIRED | UPDATED`). |
| `medicine_orders` / `medicine_order_items` | Orders with immutable price snapshots. |
| `prescription_requests` | Rx workflow state (document upload itself REQUIRES INTEGRATION). |

## 2. Price provenance rules

1. A price is displayed as **VERIFIED** only when `verification_status='VERIFIED'`
   **and** `valid_until` has not lapsed.
2. Every displayed price carries: `source`, `source_reference`,
   `verification_status`, `valid_from/until`, `last_updated`, currency, pharmacy.
3. Pharmacy submissions create a **new versioned row** (PENDING); the previous
   current row is retired via `is_current=False` — history is never overwritten.
4. A scheduled sweep (`POST /api/v1/admin/prices/expire-stale`) moves lapsed
   VERIFIED prices to **EXPIRED**; expired prices are never shown as current.
5. Unverified prices are never patient-visible.

## 3. Savings engine (`app/services/savings_service.py`)

```
comparable = VERIFIED prices ∩ current version ∩ unexpired
           ∩ pharmacy VERIFIED+ACTIVE ∩ same representation_key
potential_savings = reference_price − selected_price
```

- `representation_key = strength | dosage_form | pack_size` — prices are never
  compared across different strengths, forms, or pack sizes (spec §10).
- Statuses returned: `CALCULATED`, `INSUFFICIENT_DATA` (fewer than 2 comparable
  verified prices), `NO_COMPARISON` (all equal), `MEDICINE_NOT_FOUND`.
- When the result is not `CALCULATED`, `potential_savings` is `null`. The UI
  shows "Verified price data is insufficient to calculate savings." — never an
  invented number (spec §37).
- The response always names the reference and selected pharmacies, the source,
  and the last-updated date (transparency, spec §12).

## 4. Order state machine

```
CREATED ─┬─ CONFIRMED ─ PROCESSING ─┬─ READY_FOR_PICKUP ─ DELIVERED (terminal)
         │                          └─ OUT_FOR_DELIVERY ── DELIVERED (terminal)
         └─ PRESCRIPTION_REQUIRED ─ PRESCRIPTION_SUBMITTED ─ UNDER_REVIEW ─ CONFIRMED
CANCELLED / FAILED reachable per transition table (ORDER_TRANSITIONS).
```

- Invalid transitions are rejected server-side (`409`).
- Unit prices are **snapshotted** at creation (`price_snapshot_id`,
  `unit_price`, `snapshot_verification_status`) — later catalog changes never
  rewrite historical orders.
- Prescription-required medicines pause at `PRESCRIPTION_REQUIRED`; only a
  human pharmacy/admin review (`prescription-review`, audited) can confirm.
  Automatic approval is impossible by design.

## 5. Ordering eligibility

- Pharmacy must be VERIFIED+ACTIVE; price must be VERIFIED+current; stock
  `OUT_OF_STOCK` blocks the order; `UNKNOWN` stock is ordered but displayed
  honestly. Delivery/pickup must match pharmacy capability.

## 6. RBAC

| Role | Capabilities |
|---|---|
| PATIENT | Search medicines/pharmacies, view verified prices & savings, order, view own orders, submit prescription document reference. |
| PHARMACY_ADMIN | Own profile/inventory/prices via `/pharmacies/me/*`, own-pharmacy order transitions, prescription review. |
| SUPER_ADMIN | Medicine master data, pharmacy verification, price verification, expiration sweep, full order oversight. |

## 7. Audit trail

Audited actions: `MEDICINE_CREATED`, `PHARMACY_REGISTERED`,
`PHARMACY_VERIFIED/REJECTED/SUSPENDED`, `INVENTORY_UPDATED`,
`PRICE_SUBMITTED`, `PRICE_VERIFIED/REJECTED`, `PRICES_EXPIRED`,
`ORDER_CREATED`, `ORDER_STATUS_CHANGED`, `PRESCRIPTION_SUBMITTED`,
`PRESCRIPTION_REVIEWED`.

## 8. Data honesty

No medicine, pharmacy, price, stock, or savings number is seeded in production.
The catalog starts empty; records enter only through the verified workflows.
Every smoke/test fixture is named `(TEST FIXTURE)` / `NOT REAL`.
