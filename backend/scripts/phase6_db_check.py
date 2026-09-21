"""One-off Phase 6 database verification (read-only) against PostgreSQL.

Run: MEDISAVE_DATABASE_URL=... python scripts/phase6_db_check.py

Checks Phase 6 schema integrity (family tables, constraints, indexes), orphan
rows, and that smoke-run synthetic Phase 6 fixtures were cleaned up. Never
writes, never deletes, never touches Phase 1-5 data.
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


def rows(sql: str):
    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


# ---- counts (spec §13: tables / FKs / indexes) ----
tables = scalar("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
fks = scalar(
    "SELECT count(*) FROM information_schema.table_constraints "
    "WHERE constraint_type='FOREIGN KEY' AND constraint_schema='public'"
)
indexes = scalar("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
check("tables count", tables == 45, f"tables={tables}")
check("foreign keys count", fks == 62, f"fks={fks}")
check("indexes count", indexes == 156, f"indexes={indexes}")

# ---- family tables exist with expected constraints ----
family_constraints = rows(
    "SELECT conname, contype FROM pg_constraint con "
    "JOIN pg_class rel ON rel.oid = con.conrelid "
    "JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
    "WHERE ns.nspname='public' AND rel.relname IN "
    "('family_relationships','family_access_consents')"
)
constraint_names = {r[0]: r[1] for r in family_constraints}
expected_fks = {
    "fk_family_rel_owner", "fk_family_rel_member",
    "fk_family_consent_rel", "fk_family_consent_granter",
}
check("family FK constraints present (4)", expected_fks.issubset(constraint_names),
      str(sorted(constraint_names)))
check("unique active-relationship partial constraint/index",
      any("uq_family_active" in n for n in constraint_names)
      or scalar(
          "SELECT count(*) FROM pg_indexes WHERE schemaname='public' "
          "AND indexname='uq_family_active_relationship'"
      ) == 1,
      str(sorted(constraint_names)))

# ---- orphan checks ----
orphan_consents = scalar(
    "SELECT count(*) FROM family_access_consents c "
    "LEFT JOIN family_relationships r ON r.id = c.relationship_id WHERE r.id IS NULL"
)
check("no orphan family_access_consents", orphan_consents == 0, f"orphans={orphan_consents}")
orphan_rels = scalar(
    "SELECT count(*) FROM family_relationships r "
    "LEFT JOIN users o ON o.id = r.owner_user_id "
    "LEFT JOIN users m ON m.id = r.member_user_id "
    "WHERE o.id IS NULL OR (r.member_user_id IS NOT NULL AND m.id IS NULL)"
)
check("no orphan family_relationships (bad user refs)", orphan_rels == 0, f"orphans={orphan_rels}")
orphan_grants = scalar(
    "SELECT count(*) FROM family_access_consents c "
    "LEFT JOIN users g ON g.id = c.granted_by WHERE g.id IS NULL"
)
check("no consent rows with missing granted_by", orphan_grants == 0, f"orphans={orphan_grants}")

# ---- fixture cleanup: smoke-run synthetic family fixtures are gone ----
leftover_rels = scalar("SELECT count(*) FROM family_relationships")
leftover_consents = scalar("SELECT count(*) FROM family_access_consents")
check("no leftover family_relationships (smoke cleanup)",
      leftover_rels == 0, f"rows={leftover_rels}")
check("no leftover family_access_consents (smoke cleanup)",
      leftover_consents == 0, f"rows={leftover_consents}")
leftover_doc = scalar(
    "SELECT count(*) FROM doctors WHERE registration_number LIKE 'TMC-%' "
    "AND full_name LIKE 'Dr Smoke 6 %'"
)
check("no leftover smoke doctor fixtures", leftover_doc == 0, f"rows={leftover_doc}")
leftover_appt = scalar(
    "SELECT count(*) FROM appointments a JOIN doctors d ON d.id = a.doctor_id "
    "WHERE d.full_name LIKE 'Dr Smoke 6 %'"
)
check("no leftover smoke family appointments", leftover_appt == 0, f"rows={leftover_appt}")

# ---- Phase 1-5 seed data preserved ----
specialties = scalar("SELECT count(*) FROM specialties")
medicines = scalar("SELECT count(*) FROM medicines")
users = scalar("SELECT count(*) FROM users")
records = scalar("SELECT count(*) FROM health_records")
orders = scalar("SELECT count(*) FROM medicine_orders")
check("Phase 1 specialties preserved", specialties >= 17, f"specialties={specialties}")
check("Phase 1-5 user data preserved", users > 0, f"users={users}")
check("Phase 1-5 catalog preserved", medicines > 0, f"medicines={medicines}")
check("Phase 5 vault data preserved", records > 0, f"records={records}")
check("Phase 4 orders preserved", orders > 0, f"orders={orders}")

# ---- audit integrity: family audit rows retained even after fixture cleanup ----
family_audit = scalar(
    "SELECT count(*) FROM audit_logs WHERE resource_type='family' OR action LIKE 'FAMILY%'"
)
check("family audit trail retained (immutable history)", family_audit > 0, f"rows={family_audit}")

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  [{detail}]")
print(f"\n{len(results) - len(failed)}/{len(results)} DB checks passed")
raise SystemExit(1 if failed else 0)
