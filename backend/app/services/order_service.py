"""Medicine order state machine with immutable price snapshots (Phase 4).

Rules (spec §14, §18, §19):
- Only prices from VERIFIED pharmacies may be ordered against.
- Prescription-required medicines must move through the prescription workflow;
  the order enters PRESCRIPTION_REQUIRED and cannot be confirmed until a real
  prescription record is VERIFIED by a pharmacist/admin (never auto-approved).
- Unit prices are SNAPSHOTTED at creation; later catalog changes never rewrite
  historical order prices.
- Invalid state transitions are rejected server-side.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, joinedload

from app.models.pharmacy import (
    ORDER_TRANSITIONS,
    Medicine,
    MedicineOrder,
    MedicineOrderItem,
    MedicinePrice,
    Pharmacy,
    PharmacyInventory,
    PrescriptionRequest,
)


class OrderError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _effective_stock(row: PharmacyInventory | None) -> str:
    if row is None:
        return "UNKNOWN"
    return row.stock_status


def create_order(db: Session, payload, patient_id: str) -> MedicineOrder:
    pharmacy = db.get(Pharmacy, payload.pharmacy_id)
    if pharmacy is None or not pharmacy.is_active:
        raise OrderError("Pharmacy not found", 404)
    if pharmacy.verification_status != "VERIFIED":
        raise OrderError(
            "Orders are only accepted at VERIFIED pharmacies", 409
        )

    needs_prescription = False
    items: list[MedicineOrderItem] = []
    subtotal = 0.0
    currency = "INR"

    for item in payload.items:
        medicine = db.get(Medicine, item.medicine_id)
        if medicine is None:
            raise OrderError(f"Unknown medicine: {item.medicine_id}", 404)
        if medicine.status != "ACTIVE":
            raise OrderError(f"Medicine not orderable: {medicine.name}", 409)

        # Price source: the pharmacy's current VERIFIED price only.
        price_row = (
            db.query(MedicinePrice)
            .filter(
                MedicinePrice.pharmacy_id == pharmacy.id,
                MedicinePrice.medicine_id == medicine.id,
                MedicinePrice.verification_status == "VERIFIED",
                MedicinePrice.is_current.is_(True),
            )
            .first()
        )
        if price_row is None:
            raise OrderError(
                f"No verified price for {medicine.name} at this pharmacy; "
                "ordering is not possible without verified pricing",
                409,
            )

        # Stock honesty: block ordering when the pharmacy reports OUT_OF_STOCK
        # (spec §7). UNKNOWN stock is not silently treated as available — the
        # order is allowed but the status stays visible in the response.
        stock_row = (
            db.query(PharmacyInventory)
            .filter(
                PharmacyInventory.pharmacy_id == pharmacy.id,
                PharmacyInventory.medicine_id == medicine.id,
            )
            .first()
        )
        if _effective_stock(stock_row) == "OUT_OF_STOCK":
            raise OrderError(f"{medicine.name} is currently out of stock at this pharmacy", 409)

        if medicine.prescription_required:
            needs_prescription = True

        unit_price = float(price_row.price)
        currency = price_row.currency
        subtotal += unit_price * item.quantity
        items.append(
            MedicineOrderItem(
                medicine_id=medicine.id,
                medicine_name=medicine.name,  # snapshot
                quantity=item.quantity,
                unit_price=price_row.price,  # snapshot (Numeric)
                price_source=price_row.source,
                price_snapshot_id=price_row.id,
                snapshot_verification_status=price_row.verification_status,
            )
        )

    if payload.pickup_option and not pharmacy.pickup_supported:
        raise OrderError("This pharmacy does not support pickup", 422)
    if not payload.pickup_option and not pharmacy.delivery_supported:
        raise OrderError("This pharmacy does not support delivery", 422)

    order = MedicineOrder(
        patient_id=patient_id,
        pharmacy_id=pharmacy.id,
        status="CREATED",
        subtotal=subtotal,
        delivery_fee=0,  # delivery pricing REQUIRES INTEGRATION; never fabricated
        total=subtotal,
        currency=currency,
        delivery_address=payload.delivery_address,
        pickup_option=payload.pickup_option,
    )
    db.add(order)
    db.flush()
    for line in items:
        line.order_id = order.id
        db.add(line)

    # Prescription gate: never bypass (spec §14). The order pauses here until a
    # real prescription record is submitted and verified by pharmacy staff.
    if needs_prescription:
        order.status = "PRESCRIPTION_REQUIRED"
        db.add(PrescriptionRequest(order_id=order.id, patient_id=patient_id, status="PENDING"))

    db.flush()
    return order


def submit_prescription(db: Session, order: MedicineOrder, document_ref: str) -> PrescriptionRequest:
    """Patient submits a prescription document reference. Does NOT fabricate
    approval — the order moves to PRESCRIPTION_SUBMITTED and then UNDER_REVIEW
    only through real transitions; confirmation still requires verification."""
    if order.status != "PRESCRIPTION_REQUIRED":
        raise OrderError("This order is not awaiting a prescription", 409)
    request = (
        db.query(PrescriptionRequest)
        .filter(PrescriptionRequest.order_id == order.id)
        .first()
    )
    if request is None:
        request = PrescriptionRequest(order_id=order.id, patient_id=order.patient_id, status="SUBMITTED")
        db.add(request)
    request.status = "SUBMITTED"
    request.document_ref = document_ref
    order.status = "PRESCRIPTION_SUBMITTED"
    db.flush()
    return request


def review_prescription(
    db: Session, order: MedicineOrder, *, approved: bool, reviewer_user_id: str, note: str = ""
) -> MedicineOrder:
    """Pharmacy/admin prescription review. This is the ONLY path that moves a
    prescription order to CONFIRMED. Approval is a human decision recorded on
    the request row; it is never automatic."""
    if order.status != "PRESCRIPTION_SUBMITTED":
        raise OrderError("Order is not in PRESCRIPTION_SUBMITTED state", 409)
    request = (
        db.query(PrescriptionRequest)
        .filter(PrescriptionRequest.order_id == order.id)
        .first()
    )
    if request is None:
        raise OrderError("No prescription request found for this order", 404)
    request.status = "VERIFIED" if approved else "REJECTED"
    request.reviewed_by_user_id = reviewer_user_id
    request.review_note = note
    if approved:
        order.status = "CONFIRMED"
    else:
        order.status = "CANCELLED"
    db.flush()
    return order


def transition_order(db: Session, order: MedicineOrder, new_status: str, actor) -> MedicineOrder:
    """Apply a validated state transition (spec §18)."""
    allowed = ORDER_TRANSITIONS.get(order.status, ())
    if new_status not in allowed:
        raise OrderError(
            f"Invalid transition {order.status} -> {new_status}. "
            f"Allowed: {list(allowed) or 'none (terminal state)'}",
            409,
        )
    order.status = new_status
    order.updated_at = datetime.now(UTC)
    db.flush()
    return order


def get_owned_order(db: Session, order_id: str, user) -> MedicineOrder:
    order = (
        db.query(MedicineOrder)
        .options(joinedload(MedicineOrder.items))
        .filter(MedicineOrder.id == order_id)
        .first()
    )
    if order is None:
        raise OrderError("Order not found", 404)
    is_admin = "SUPER_ADMIN" in user.role_ids
    owns_pharmacy = False
    if "PHARMACY_ADMIN" in user.role_ids:
        pharmacy = db.get(Pharmacy, order.pharmacy_id)
        owns_pharmacy = pharmacy is not None and pharmacy.admin_user_id == user.id
    if order.patient_id != user.id and not (is_admin or owns_pharmacy):
        # Do not leak existence of other users' orders (spec §32).
        raise OrderError("Order not found", 404)
    return order
