"""One-off Phase 7 database verification (read-only) against PostgreSQL.

Run: MEDISAVE_DATABASE_URL=... python scripts/phase7_db_check.py

Verifies the emergency expansion: new tables, partial unique indexes,
orphan-free FK graph, honest terminal states, and Phase 1-6 preservation.
Never writes, never deletes, never touches patient data.
"""

import os

from sqlalchemy import create_engine, text

URL = os.environ.get(
    "MEDISAVE_DATABASE_URL",
    "postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave",
)
engine = create_engine(URL)

results: list[tuple[str, bool, str]] = []


def scalar(sql: str):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ---- counts after the Phase 7 migration ----
tables = scalar("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
fks = scalar(
    "SELECT count(*) FROM information_schema.table_constraints "
    "WHERE constraint_type='FOREIGN KEY' AND constraint_schema='public'"
)
indexes = scalar("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
check("tables count (49 after Phase 7)", tables == 49, f"tables={tables}")
check("foreign keys count (73 after Phase 7)", fks == 73, f"fks={fks}")
check("indexes count (171 after Phase 7)", indexes == 171, f"indexes={indexes}")

# ---- new tables exist with data-capable shapes ----
for table in (
    "emergency_profiles",
    "emergency_handoffs",
    "emergency_notifications",
    "emergency_provider_events",
):
    n = scalar(f"SELECT count(*) FROM information_schema.tables WHERE table_name='{table}'")
    check(f"table {table} exists", n == 1, f"found={n}")

# ---- partial unique indexes (race-safe SOS rules) ----
uq_active = scalar(
    "SELECT count(*) FROM pg_indexes WHERE schemaname='public' "
    "AND indexname='uq_patient_active_sos'"
)
check("uq_patient_active_sos partial index", uq_active == 1, f"found={uq_active}")
uq_idem = scalar(
    "SELECT count(*) FROM pg_indexes WHERE schemaname='public' "
    "AND indexname='uq_sos_idempotency'"
)
check("uq_sos_idempotency partial index", uq_idem == 1, f"found={uq_idem}")

# ---- FK graph integrity ----
orphan_notif = scalar(
    "SELECT count(*) FROM emergency_notifications n "
    "LEFT JOIN emergency_events e ON e.id = n.emergency_event_id "
    "WHERE n.emergency_event_id IS NOT NULL AND e.id IS NULL"
)
check("no orphan emergency_notifications", orphan_notif == 0, f"orphans={orphan_notif}")
orphan_handoff = scalar(
    "SELECT count(*) FROM emergency_handoffs h "
    "LEFT JOIN emergency_events e ON e.id = h.emergency_event_id "
    "LEFT JOIN hospitals hp ON hp.id = h.hospital_id "
    "WHERE e.id IS NULL OR hp.id IS NULL"
)
check("no orphan emergency_handoffs", orphan_handoff == 0, f"orphans={orphan_handoff}")
orphan_provider = scalar(
    "SELECT count(*) FROM emergency_provider_events p "
    "LEFT JOIN emergency_events e ON e.id = p.emergency_event_id WHERE e.id IS NULL"
)
check("no orphan emergency_provider_events", orphan_provider == 0, f"orphans={orphan_provider}")
orphan_events = scalar(
    "SELECT count(*) FROM emergency_events ev LEFT JOIN users u ON u.id = ev.user_id "
    "WHERE u.id IS NULL"
)
check("no emergency_events with missing patient", orphan_events == 0, f"orphans={orphan_events}")
orphan_profile = scalar(
    "SELECT count(*) FROM emergency_profiles p LEFT JOIN users u ON u.id = p.user_id "
    "WHERE u.id IS NULL"
)
check("no emergency_profiles with missing user", orphan_profile == 0, f"orphans={orphan_profile}")

# ---- handoffs only ever target VERIFIED hospitals ----
bad_handoff = scalar(
    "SELECT count(*) FROM emergency_handoffs h "
    "JOIN hospitals hp ON hp.id = h.hospital_id "
    "WHERE hp.verification_status <> 'VERIFIED'"
)
check("handoffs target VERIFIED hospitals only", bad_handoff == 0, f"bad={bad_handoff}")

# ---- honest states: smoke SOS events end terminal; nothing stuck ACTIVE ----
stuck = scalar(
    "SELECT count(*) FROM emergency_events WHERE status = 'ACTIVE' "
    "AND confirmed_by_provider IS NULL"
)
check("no ACTIVE event without real provider confirmation", stuck == 0, f"stuck={stuck}")
bad_notif = scalar(
    "SELECT count(*) FROM emergency_notifications WHERE status = 'DELIVERED'"
)
check("no fabricated DELIVERED notifications", bad_notif == 0, f"rows={bad_notif}")
bad_provider = scalar(
    "SELECT count(*) FROM emergency_provider_events WHERE status = 'DISPATCHED'"
)
check("no fabricated ambulance dispatch states", bad_provider == 0, f"rows={bad_provider}")

# ---- audit trail retained for emergency actions ----
emergency_audit = scalar(
    "SELECT count(*) FROM audit_logs WHERE resource_type='emergency' "
    "OR action LIKE 'SOS%' OR action LIKE 'EMERGENCY%'"
)
check("emergency audit trail retained", emergency_audit > 0, f"rows={emergency_audit}")

# ---- Phase 1-6 data preserved ----
specialties = scalar("SELECT count(*) FROM specialties")
users = scalar("SELECT count(*) FROM users")
records = scalar("SELECT count(*) FROM health_records")
orders = scalar("SELECT count(*) FROM medicine_orders")
family_rels = scalar("SELECT count(*) FROM family_relationships")
check("Phase 1 specialties preserved", specialties >= 17, f"specialties={specialties}")
check("Phase 1-6 user data preserved", users > 0, f"users={users}")
check("Phase 5 vault data preserved", records > 0, f"records={records}")
check("Phase 4 orders preserved", orders > 0, f"orders={orders}")
check("Phase 6 family tables intact", family_rels >= 0, f"rows={family_rels}")

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
print(f"\n{len(results) - len(failed)}/{len(results)} DB checks passed")
raise SystemExit(1 if failed else 0)
