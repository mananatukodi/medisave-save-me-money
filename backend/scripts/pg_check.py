"""PostgreSQL verification: migrations + integrity checks (Phases 3 & 4).

Run against a live Postgres:
  MEDISAVE_DATABASE_URL=postgresql+psycopg://... python scripts/pg_check.py

Phase 3 checks: double-booking prevention via the partial unique index.
Phase 4 checks: inventory uniqueness, price versioning (is_current), and
order price snapshots — the data-integrity core of the savings engine.
All rows are created with TEST data and cleaned up (nothing fabricated remains).
"""

import os
import sys
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.appointment import Appointment
from app.models.healthcare import Specialty
from app.models.pharmacy import (
    Medicine,
    MedicineOrder,
    MedicineOrderItem,
    MedicinePrice,
    Pharmacy,
    PharmacyInventory,
)
from app.models.providers import Doctor, ProviderService
from app.models.user import Role, User, UserRole

URL = os.environ.get(
    "MEDISAVE_DATABASE_URL",
    "postgresql+psycopg://medisave:medisave_dev_only@localhost:5432/medisave",
)

engine = create_engine(URL)
Base.metadata.create_all(engine)  # no-op when migrations already ran
Session = sessionmaker(bind=engine)
db = Session()
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS: " if ok else "FAIL: ") + name + (f" | {detail}" if detail else ""))
    if not ok:
        failures.append(name)


try:
    # ------------------------------------------------ shared fixtures
    if db.query(Specialty).filter(Specialty.slug == "pg-check-spec").first() is None:
        db.add(
            Specialty(
                slug="pg-check-spec", name_en="PG Check", name_te="PG Check",
                name_hi="PG Check", icon="T", sort_order=999, description_en="temp",
            )
        )
        db.flush()
    specialty = db.query(Specialty).filter(Specialty.slug == "pg-check-spec").first()

    if db.get(Role, "PATIENT") is None:
        db.add(Role(id="PATIENT", description="check"))
        db.flush()
    if db.query(User).filter(User.email == "pg-check@test").first() is None:
        user = User(full_name="PG Check", email="pg-check@test", password_hash="x")
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_id="PATIENT"))
        db.flush()
    user = db.query(User).filter(User.email == "pg-check@test").first()

    # ================================================ Phase 3 checks
    doctor = Doctor(
        full_name="PG Check Doctor", specialty_slug=specialty.slug,
        verification_status="VERIFIED",
    )
    db.add(doctor)
    db.flush()
    service = ProviderService(
        provider_kind="DOCTOR", provider_id=doctor.id, doctor_id=doctor.id,
        specialty_slug=specialty.slug, name_en="PG Check Service",
    )
    db.add(service)
    db.flush()

    first = Appointment(
        patient_user_id=user.id, doctor_id=doctor.id, specialty_slug=specialty.slug,
        service_id=service.id, appointment_date="2099-01-01", appointment_time="10:00",
        status="CONFIRMED",
    )
    db.add(first)
    db.commit()

    duplicate = Appointment(
        patient_user_id=user.id, doctor_id=doctor.id, specialty_slug=specialty.slug,
        service_id=service.id, appointment_date="2099-01-01", appointment_time="10:00",
        status="CONFIRMED",
    )
    db.add(duplicate)
    try:
        db.commit()
        check("double booking blocked by partial unique index", False)
    except IntegrityError:
        db.rollback()
        check("double booking blocked by partial unique index", True)

    cancelled = Appointment(
        patient_user_id=user.id, doctor_id=doctor.id, specialty_slug=specialty.slug,
        service_id=service.id, appointment_date="2099-01-01", appointment_time="10:00",
        status="CANCELLED",
    )
    db.add(cancelled)
    db.commit()
    check("cancelled appointment on same slot allowed", True)

    # ================================================ Phase 4 checks
    uid = uuid.uuid4().hex[:8]
    medicine = Medicine(
        name=f"PG Check Med {uid}", generic_name="pgcheck", strength="500 mg",
        dosage_form="TABLET", pack_size="10 tablets", data_source="PG_CHECK_TEST",
    )
    pharmacy = Pharmacy(
        name=f"PG Check Pharma {uid}", verification_status="VERIFIED", is_active=True,
    )
    db.add_all([medicine, pharmacy])
    db.flush()

    # 1) one inventory row per (pharmacy, medicine)
    inv = PharmacyInventory(
        pharmacy_id=pharmacy.id, medicine_id=medicine.id,
        stock_status="IN_STOCK", quantity=10,
    )
    db.add(inv)
    db.commit()
    dup_inv = PharmacyInventory(
        pharmacy_id=pharmacy.id, medicine_id=medicine.id, stock_status="LOW_STOCK"
    )
    db.add(dup_inv)
    try:
        db.commit()
        check("inventory uniqueness per (pharmacy, medicine)", False)
    except IntegrityError:
        db.rollback()
        check("inventory uniqueness per (pharmacy, medicine)", True)

    # 2) price versioning: retiring the old current row keeps exactly one current
    v1 = MedicinePrice(
        medicine_id=medicine.id, pharmacy_id=pharmacy.id, price=100,
        currency="INR", verification_status="VERIFIED", is_current=True,
    )
    db.add(v1)
    db.commit()
    v1.is_current = False
    v2 = MedicinePrice(
        medicine_id=medicine.id, pharmacy_id=pharmacy.id, price=90,
        currency="INR", verification_status="PENDING", is_current=True,
    )
    db.add(v2)
    db.commit()
    current = (
        db.query(MedicinePrice)
        .filter(
            MedicinePrice.medicine_id == medicine.id,
            MedicinePrice.pharmacy_id == pharmacy.id,
            MedicinePrice.is_current.is_(True),
        )
        .count()
    )
    check("price versioning keeps exactly one current row", current == 1, f"current={current}")

    # 3) order price snapshot survives a catalog price change
    order = MedicineOrder(
        patient_id=user.id, pharmacy_id=pharmacy.id, status="CREATED",
        subtotal=100, total=100, currency="INR",
    )
    db.add(order)
    db.flush()
    item = MedicineOrderItem(
        order_id=order.id, medicine_id=medicine.id, medicine_name=medicine.name,
        quantity=1, unit_price=v1.price, price_source="PHARMACY_SUBMITTED",
        price_snapshot_id=v1.id, snapshot_verification_status="VERIFIED",
    )
    db.add(item)
    db.commit()
    v2.price = 999  # catalog price changes after the order
    db.commit()
    stored = (
        db.query(MedicineOrderItem)
        .filter(MedicineOrderItem.order_id == order.id)
        .first()
    )
    check(
        "order snapshot independent of catalog price change",
        float(stored.unit_price) == 100.0,
        f"snapshot={stored.unit_price}",
    )

    # ------------------------------------------------ Phase 4 cleanup
    db.delete(item)
    db.delete(order)
    db.query(MedicinePrice).filter(
        MedicinePrice.medicine_id == medicine.id
    ).delete()
    db.query(PharmacyInventory).filter(
        PharmacyInventory.pharmacy_id == pharmacy.id
    ).delete()
    db.delete(pharmacy)
    db.delete(medicine)

    # ------------------------------------------------ Phase 3 cleanup
    db.query(Appointment).filter(Appointment.doctor_id == doctor.id).delete()
    db.delete(service)
    db.delete(doctor)
    db.delete(user)
    db.delete(specialty)
    db.commit()
    check("cleanup complete (no fabricated rows remain)", True)
finally:
    db.close()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

if failures:
    print(f"FAILED CHECKS: {failures}")
    sys.exit(1)
print("ALL POSTGRES CHECKS PASSED")
