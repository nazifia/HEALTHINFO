"""Pharmacy: stock in, stock out, money split, claim settled.

The checks that matter are the ones where a bug costs someone money or a drug:
first-expiry-first-out allocation, an all-or-nothing basket, the patient/HMO
split adding back to the total, and a cancelled sale putting stock back where
it came from.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import Role, User
from apps.governance.models import AuditLog
from apps.patients.models import Patient
from apps.pharmacy.models import (
    HMO,
    Claim,
    HmoEnrollment,
    HmoItemRule,
    PreAuthorization,
    Notification,
    PreAuthorizationItem,
    PurchaseOrder,
    PurchaseOrderLine,
    Sale,
    SaleItem,
    SalePayment,
    StockBatch,
    StockItem,
    StockMovement,
    Supplier,
    TillSession,
    receive_stock,
)
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c


@pytest.fixture
def pharmacy(db_clean):
    """A tenant with an admin, a pharmacist, and one item stocked in two batches.

    The older batch (30 units, expires in 10 days) must be the one that sells
    first; the newer one (50 units, a year out) only gets touched when the
    older runs out.
    """
    tenant = Tenant.objects.create(name="Ade Pharmacy", slug="ade")
    admin = User.objects.create_user(phone="08030000201", password="x",
                                     tenant=tenant, role=Role.TENANT_ADMIN,
                                     username="admin")
    staff = User.objects.create_user(phone="08030000202", password="x",
                                     tenant=tenant, role=Role.PHARMACIST,
                                     username="staff")
    item = StockItem.all_objects.create(
        tenant=tenant, name="Paracetamol 500mg", sku="PARA500",
        unit="tablet", cost_price=Decimal("5.00"), unit_price=Decimal("12.50"),
        reorder_level=20,
    )
    supplier = Supplier.all_objects.create(tenant=tenant, name="Emzor")
    today = timezone.localdate()
    old = receive_stock(item, 30, batch_number="B-OLD",
                        expiry_date=today + timedelta(days=10),
                        cost_price=Decimal("4.00"), supplier=supplier)
    new = receive_stock(item, 50, batch_number="B-NEW",
                        expiry_date=today + timedelta(days=365),
                        cost_price=Decimal("5.00"), supplier=supplier)
    return {"tenant": tenant, "admin": admin, "staff": staff, "item": item,
            "supplier": supplier, "old": old, "new": new}


def test_receive_books_stock_and_ledger(pharmacy):
    item = pharmacy["item"]
    assert item.quantity_on_hand == 80
    receipts = StockMovement.all_objects.filter(
        item=item, kind=StockMovement.Kind.RECEIPT
    )
    assert [m.quantity for m in receipts.order_by("id")] == [30, 50]

    # The same batch arriving again tops it up rather than splitting in two.
    receive_stock(item, 20, batch_number="B-OLD")
    assert StockBatch.all_objects.filter(item=item).count() == 2
    batch = StockBatch.all_objects.get(item=item, batch_number="B-OLD")
    assert (batch.quantity, batch.quantity_received) == (50, 50)


def test_sale_dispenses_first_expiry_first_out(pharmacy):
    """40 tablets: 30 from the batch that expires soonest, 10 from the next."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 40}],
    }, format="json")
    assert response.status_code == 201, response.content
    body = response.json()

    sale = Sale.all_objects.get(pk=body["id"])
    lines = list(SaleItem.all_objects.filter(sale=sale).order_by("id"))
    assert [(l.batch.batch_number, l.quantity) for l in lines] == [
        ("B-OLD", 30), ("B-NEW", 10)
    ]
    # Cost price is captured per batch, so margin survives a later price change.
    assert [l.cost_price for l in lines] == [Decimal("4.00"), Decimal("5.00")]

    pharmacy["old"].refresh_from_db()
    pharmacy["new"].refresh_from_db()
    assert (pharmacy["old"].quantity, pharmacy["new"].quantity) == (0, 40)

    assert sale.total == Decimal("500.00")  # 40 x 12.50
    # Cash sale: the patient owes all of it, the HMO none.
    assert (sale.patient_payable, sale.hmo_payable) == (Decimal("500.00"),
                                                        Decimal("0.00"))
    assert sale.status == Sale.Status.PENDING
    assert StockMovement.all_objects.filter(
        sale=sale, kind=StockMovement.Kind.DISPENSE
    ).count() == 2


def test_expired_stock_is_never_dispensed(pharmacy):
    """An expired batch stays on the books but cannot be sold."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    old = pharmacy["old"]
    old.expiry_date = timezone.localdate() - timedelta(days=1)
    old.save(update_fields=["expiry_date"])

    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 30}],
    }, format="json")
    assert response.status_code == 201, response.content
    sale = Sale.all_objects.get(pk=response.json()["id"])
    lines = SaleItem.all_objects.filter(sale=sale)
    assert [l.batch.batch_number for l in lines] == ["B-NEW"]
    old.refresh_from_db()
    assert old.quantity == 30  # untouched, still counted as stock on hand
    assert item.quantity_on_hand == 50


def test_short_stock_rejects_the_whole_basket(pharmacy):
    """A basket is all or nothing — the line that fits must not be dispensed
    when a later line cannot be."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    other = StockItem.all_objects.create(tenant=tenant, name="Amoxicillin",
                                         unit_price=Decimal("30.00"))
    receive_stock(other, 5, batch_number="AM-1")

    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 10},
                  {"item": other.id, "quantity": 50}],
    }, format="json")
    assert response.status_code == 400, response.content
    assert "only 5" in response.json()["message"]
    # Nothing committed: no sale, no movement, the first item's stock intact.
    assert Sale.all_objects.count() == 0
    assert item.quantity_on_hand == 80
    assert StockMovement.all_objects.filter(
        kind=StockMovement.Kind.DISPENSE
    ).count() == 0


def test_hmo_sale_splits_the_bill_and_raises_a_claim(pharmacy):
    """70% cover: the patient pays the co-payment, the HMO is billed the rest,
    and the two sides add back to the total."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ada",
                                         last_name="Obi")
    hmo = HMO.all_objects.create(tenant=tenant, name="Hygeia",
                                 coverage_percent=Decimal("70.00"))
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="HY-1"
    )

    staff = _client(pharmacy["staff"], tenant)
    response = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 10}],
    }, format="json")
    assert response.status_code == 201, response.content
    sale = Sale.all_objects.get(pk=response.json()["id"])
    assert sale.total == Decimal("125.00")
    assert sale.hmo_payable == Decimal("87.50")
    assert sale.patient_payable == Decimal("37.50")
    assert sale.patient_payable + sale.hmo_payable == sale.total

    claim = Claim.all_objects.get(sale=sale)
    assert (claim.hmo_id, claim.amount, claim.status) == (
        hmo.id, Decimal("87.50"), Claim.Status.DRAFT)

    # The patient's co-payment settles the sale; the HMO side rides on the claim.
    # The patient hands over 50.00 for a 37.50 co-payment: only what is owed is
    # banked, the rest is change counted back over the counter.
    paid = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "50.00"}, format="json")
    assert paid.status_code == 200, paid.content
    assert paid.json()["change_due"] == "12.50"
    sale.refresh_from_db()
    assert sale.status == Sale.Status.PAID and sale.balance_due == Decimal("0.00")
    assert sale.amount_paid == Decimal("37.50")
    assert sale.amount_tendered == Decimal("50.00")
    assert sale.change_due == Decimal("12.50")

    # A settled sale takes no more money: nothing is owed, so there is nothing
    # to bank and no reason to take cash for it.
    again = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                       {"amount": "10.00"}, format="json")
    assert again.status_code == 400, again.content
    sale.refresh_from_db()
    assert sale.amount_paid == Decimal("37.50")


def test_claim_lifecycle_and_who_may_settle(pharmacy):
    """Staff submit; only the admin approves, rejects or banks money."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Bola",
                                         last_name="Ade")
    hmo = HMO.all_objects.create(tenant=tenant, name="Reliance",
                                 coverage_percent=Decimal("100.00"))
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="RL-9"
    )
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)
    sale = Sale.all_objects.get(pk=staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 8}],
    }, format="json").json()["id"])
    claim = Claim.all_objects.get(sale=sale)
    assert claim.amount == Decimal("100.00")

    # Approving before submitting is not a state the claim can be in.
    assert admin.post(f"/api/pharmacy/claims/{claim.pk}/approve/", {},
                      format="json").status_code == 400

    assert staff.post(f"/api/pharmacy/claims/{claim.pk}/submit/", {},
                      format="json").status_code == 200
    # Staff may send a claim, but not decide it.
    assert staff.post(f"/api/pharmacy/claims/{claim.pk}/approve/",
                      {"amount": "100.00"}, format="json").status_code == 403

    # The insurer approves less than was claimed, then pays that in two parts.
    assert admin.post(f"/api/pharmacy/claims/{claim.pk}/approve/",
                      {"amount": "80.00"}, format="json").status_code == 200
    claim.refresh_from_db()
    assert (claim.status, claim.amount_approved) == (Claim.Status.APPROVED,
                                                     Decimal("80.00"))
    assert claim.outstanding == Decimal("80.00")

    admin.post(f"/api/pharmacy/claims/{claim.pk}/pay/", {"amount": "50.00"},
               format="json")
    claim.refresh_from_db()
    # Part-payment leaves the claim open — the balance is still chased.
    assert (claim.status, claim.amount_paid) == (Claim.Status.APPROVED,
                                                 Decimal("50.00"))
    admin.post(f"/api/pharmacy/claims/{claim.pk}/pay/", {"amount": "30.00"},
               format="json")
    claim.refresh_from_db()
    assert claim.status == Claim.Status.PAID and claim.settled_at is not None

    # Approving more than was claimed is not an accounting the pharmacy accepts.
    other = Claim.all_objects.create(tenant=tenant, sale=Sale.all_objects.create(
        tenant=tenant), hmo=hmo, amount=Decimal("10.00"),
        status=Claim.Status.SUBMITTED)
    assert admin.post(f"/api/pharmacy/claims/{other.pk}/approve/",
                      {"amount": "999.00"}, format="json").status_code == 400


def test_cancelled_sale_returns_stock_to_its_own_batch(pharmacy):
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Chi",
                                         last_name="Eze")
    hmo = HMO.all_objects.create(tenant=tenant, name="AXA")
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="AX-3"
    )
    staff = _client(pharmacy["staff"], tenant)
    sale = Sale.all_objects.get(pk=staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 40}],
    }, format="json").json()["id"])
    claim = Claim.all_objects.get(sale=sale)

    cancelled = staff.post(f"/api/pharmacy/sales/{sale.pk}/cancel/",
                           {"reason": "wrong drug"}, format="json")
    assert cancelled.status_code == 200, cancelled.content
    sale.refresh_from_db()
    claim.refresh_from_db()
    assert sale.status == Sale.Status.CANCELLED
    assert claim.status == Claim.Status.CANCELLED

    # Each batch gets back exactly what it gave — not 40 units onto whichever
    # batch happened to be first.
    pharmacy["old"].refresh_from_db()
    pharmacy["new"].refresh_from_db()
    assert (pharmacy["old"].quantity, pharmacy["new"].quantity) == (30, 50)
    assert StockMovement.all_objects.filter(
        sale=sale, kind=StockMovement.Kind.RETURN
    ).count() == 2


def test_adjustment_is_admin_only_and_logged(pharmacy):
    tenant = pharmacy["tenant"]
    batch = pharmacy["old"]
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)
    url = f"/api/pharmacy/batches/{batch.pk}/adjust/"

    assert staff.post(url, {"quantity": 25, "reason": "count"},
                      format="json").status_code == 403
    assert admin.post(url, {"quantity": 25, "reason": "monthly count"},
                      format="json").status_code == 200
    batch.refresh_from_db()
    assert batch.quantity == 25
    movement = StockMovement.all_objects.filter(
        batch=batch, kind=StockMovement.Kind.ADJUSTMENT
    ).get()
    assert (movement.quantity, movement.reason) == (-5, "monthly count")


def test_low_stock_expiring_and_valuation(pharmacy):
    tenant = pharmacy["tenant"]
    # An item that has never been stocked is the one most in need of ordering.
    StockItem.all_objects.create(tenant=tenant, name="ORS sachet",
                                 reorder_level=10, unit_price=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)

    low = staff.get("/api/pharmacy/items/low-stock/")
    assert low.status_code == 200, low.content
    assert [row["name"] for row in low.json()] == ["ORS sachet"]

    expiring = staff.get("/api/pharmacy/batches/expiring/?days=30").json()
    assert [row["batch_number"] for row in expiring] == ["B-OLD"]

    value = staff.get("/api/pharmacy/items/valuation/").json()
    # 30 x 4.00 + 50 x 5.00 cost; 80 x 12.50 retail.
    assert Decimal(value["cost_value"]) == Decimal("370.00")
    assert Decimal(value["retail_value"]) == Decimal("1000.00")


def test_another_tenant_sees_none_of_it(pharmacy):
    other_tenant = Tenant.objects.create(name="Rival", slug="rival")
    outsider = User.objects.create_user(phone="08030000299", password="x",
                                        tenant=other_tenant,
                                        role=Role.PHARMACIST)
    client = _client(outsider, other_tenant)
    assert client.get("/api/pharmacy/items/").json()["count"] == 0
    assert client.get(
        f"/api/pharmacy/items/{pharmacy['item'].pk}/"
    ).status_code == 404


def test_non_pharmacy_roles_are_shut_out(pharmacy):
    """Stock, prices and margins are not open to every tenant member."""
    tenant = pharmacy["tenant"]
    nurse = User.objects.create_user(phone="08030000203", password="x",
                                     tenant=tenant, role=Role.NURSE)
    assert _client(nurse, tenant).get("/api/pharmacy/items/").status_code == 403


def test_hmo_sale_needs_a_valid_membership(pharmacy):
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ola",
                                         last_name="Ade")
    hmo = HMO.all_objects.create(tenant=tenant, name="Lapsed HMO")
    expired = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="LP-1",
        valid_to=timezone.localdate() - timedelta(days=1),
    )
    staff = _client(pharmacy["staff"], tenant)

    no_card = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "items": [{"item": item.id, "quantity": 1}],
    }, format="json")
    assert no_card.status_code == 400

    lapsed = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": expired.id,
        "items": [{"item": item.id, "quantity": 1}],
    }, format="json")
    assert lapsed.status_code == 400
    assert Sale.all_objects.count() == 0


def _hmo_sale(pharmacy, hmo, quantity, member_number):
    """One fully-covered HMO sale, returning its claim."""
    tenant = pharmacy["tenant"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Pat",
                                         last_name=member_number)
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number=member_number
    )
    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": pharmacy["item"].id, "quantity": quantity}],
    }, format="json")
    assert response.status_code == 201, response.content
    return Claim.all_objects.get(sale_id=response.json()["id"])


def test_purchase_order_receives_in_parts(pharmacy):
    """Order 100, take 60 now and 40 later; the order says so at each step."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)

    created = staff.post("/api/pharmacy/purchase-orders/", {
        "supplier": pharmacy["supplier"].id,
        "items": [{"item": item.id, "quantity_ordered": 100,
                   "unit_cost": "4.50"}],
    }, format="json")
    assert created.status_code == 201, created.content
    order = PurchaseOrder.all_objects.get(pk=created.json()["id"])
    assert order.status == PurchaseOrder.Status.DRAFT
    assert order.total_cost == Decimal("450.00")
    line = PurchaseOrderLine.all_objects.get(order=order)

    assert staff.post(f"/api/pharmacy/purchase-orders/{order.pk}/submit/", {},
                      format="json").status_code == 200
    order.refresh_from_db()
    assert order.status == PurchaseOrder.Status.SUBMITTED

    part = staff.post(f"/api/pharmacy/purchase-orders/{order.pk}/receive/", {
        "line": line.pk, "quantity": 60, "batch_number": "PO-1",
        "expiry_date": str(timezone.localdate() + timedelta(days=400)),
        "unit_cost": "4.75",
    }, format="json")
    assert part.status_code == 201, part.content
    line.refresh_from_db()
    order.refresh_from_db()
    assert (line.quantity_received, line.outstanding) == (60, 40)
    assert order.status == PurchaseOrder.Status.PARTIAL
    # Real stock arrived, priced at the invoice and attributed to the supplier.
    batch = StockBatch.all_objects.get(item=item, batch_number="PO-1")
    assert (batch.quantity, batch.cost_price) == (60, Decimal("4.75"))
    assert batch.supplier_id == pharmacy["supplier"].id
    assert item.quantity_on_hand == 140

    # A supplier who ships more than was ordered has changed the order.
    over = staff.post(f"/api/pharmacy/purchase-orders/{order.pk}/receive/", {
        "line": line.pk, "quantity": 41, "batch_number": "PO-2",
    }, format="json")
    assert over.status_code == 400
    assert "40 unit(s) outstanding" in over.json()["message"]

    staff.post(f"/api/pharmacy/purchase-orders/{order.pk}/receive/", {
        "line": line.pk, "quantity": 40, "batch_number": "PO-2",
    }, format="json")
    order.refresh_from_db()
    assert order.status == PurchaseOrder.Status.RECEIVED
    # Nothing outstanding is left to cancel.
    assert staff.post(f"/api/pharmacy/purchase-orders/{order.pk}/cancel/", {},
                      format="json").status_code == 400


def test_purchase_order_lines_freeze_once_sent(pharmacy):
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)
    order_id = staff.post("/api/pharmacy/purchase-orders/", {
        "supplier": pharmacy["supplier"].id,
        "items": [{"item": item.id, "quantity_ordered": 10, "unit_cost": "4.00"}],
    }, format="json").json()["id"]

    # A draft can still be rewritten.
    redrafted = staff.patch(f"/api/pharmacy/purchase-orders/{order_id}/", {
        "items": [{"item": item.id, "quantity_ordered": 25, "unit_cost": "4.00"}],
    }, format="json")
    assert redrafted.status_code == 200, redrafted.content
    assert PurchaseOrderLine.all_objects.get(order_id=order_id).quantity_ordered == 25

    staff.post(f"/api/pharmacy/purchase-orders/{order_id}/submit/", {},
               format="json")
    frozen = staff.patch(f"/api/pharmacy/purchase-orders/{order_id}/", {
        "items": [{"item": item.id, "quantity_ordered": 99, "unit_cost": "4.00"}],
    }, format="json")
    assert frozen.status_code == 400


def test_receipt_prints_the_sale(pharmacy):
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)
    sale_id = staff.post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 2}],
    }, format="json").json()["id"]
    staff.post(f"/api/pharmacy/sales/{sale_id}/pay/", {"amount": "25.00"},
               format="json")

    response = staff.get(f"/api/pharmacy/sales/{sale_id}/receipt/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    html = response.content.decode()
    sale = Sale.all_objects.get(pk=sale_id)
    assert sale.reference in html
    assert "Paracetamol 500mg" in html and "B-OLD" in html
    assert "Ade Pharmacy" in html

    # A cancelled sale still prints, stamped so it cannot pass as a live receipt.
    staff.post(f"/api/pharmacy/sales/{sale_id}/cancel/", {}, format="json")
    assert "CANCELLED" in staff.get(
        f"/api/pharmacy/sales/{sale_id}/receipt/"
    ).content.decode()


def test_insured_patient_is_billed_without_naming_the_card(pharmacy):
    """The counter picks the patient; the server finds the scheme they are on,
    and an auto-submitting insurer gets the claim there and then."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Bola",
                                         last_name="Eze")
    hmo = HMO.all_objects.create(tenant=tenant, name="Reliance",
                                 coverage_percent=Decimal("80.00"),
                                 auto_submit_claims=True)
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="RL-1"
    )

    staff = _client(pharmacy["staff"], tenant)
    response = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "items": [{"item": item.id, "quantity": 10}],
    }, format="json")
    assert response.status_code == 201, response.content
    sale = Sale.all_objects.get(pk=response.json()["id"])
    assert sale.enrollment_id == enrollment.id
    assert sale.hmo_payable == Decimal("100.00")

    claim = Claim.all_objects.get(sale=sale)
    assert claim.status == Claim.Status.SUBMITTED
    assert claim.submitted_at is not None

    # A second valid scheme makes the choice the pharmacist's, not the server's.
    other = HMO.all_objects.create(tenant=tenant, name="AXA",
                                   coverage_percent=Decimal("50.00"))
    HmoEnrollment.all_objects.create(tenant=tenant, patient=patient, hmo=other,
                                     member_number="AX-1")
    ambiguous = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "items": [{"item": item.id, "quantity": 1}],
    }, format="json")
    assert ambiguous.status_code == 400
    assert "more than one scheme" in str(ambiguous.json()["errors"]["enrollment"])


def test_drawer_reconciles_the_cash_that_went_through_it(pharmacy):
    """Open with a float, sell for cash, count at close - variance is recorded."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)

    opened = staff.post("/api/pharmacy/till-sessions/",
                        {"opening_float": "5000.00"}, format="json")
    assert opened.status_code == 201, opened.content
    till_id = opened.json()["id"]

    # One drawer at a time: a second open is refused, not silently duplicated.
    again = staff.post("/api/pharmacy/till-sessions/",
                       {"opening_float": "100.00"}, format="json")
    assert again.status_code == 400, again.content

    sale_response = staff.post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 4}],
    }, format="json")
    assert sale_response.status_code == 201, sale_response.content
    sale = Sale.all_objects.get(pk=sale_response.json()["id"])
    assert sale.total == Decimal("50.00")  # 4 x 12.50

    # The patient hands over 100.00 for a 50.00 bill: both notes and change
    # pass through the drawer, so it is 50.00 heavier than it was.
    paid = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "100.00"}, format="json")
    assert paid.status_code == 200, paid.content
    assert paid.json()["change_due"] == "50.00"

    till = TillSession.all_objects.get(pk=till_id)
    assert (till.cash_in, till.change_out) == (Decimal("100.00"), Decimal("50.00"))
    assert till.expected_amount == Decimal("5050.00")
    assert till.variance is None  # nothing counted yet
    payment = SalePayment.all_objects.get(sale=sale)
    assert (payment.method, payment.till_session_id) == ("cash", till_id)
    assert (payment.tendered, payment.applied, payment.change) == (
        Decimal("100.00"), Decimal("50.00"), Decimal("50.00"))

    # Counted 20.00 short: the shortfall is recorded, never corrected away.
    closed = staff.post(f"/api/pharmacy/till-sessions/{till_id}/close/",
                        {"amount": "5030.00", "notes": "Two notes missing."},
                        format="json")
    assert closed.status_code == 200, closed.content
    assert closed.json()["variance"] == "-20.00"
    till.refresh_from_db()
    assert till.status == TillSession.Status.CLOSED and till.closed_at is not None
    assert till.counted_amount == Decimal("5030.00")

    # A closed drawer stays closed, and takes no second count.
    recount = staff.post(f"/api/pharmacy/till-sessions/{till_id}/close/",
                         {"amount": "5050.00"}, format="json")
    assert recount.status_code == 400, recount.content


def test_payment_without_an_open_drawer_still_goes_through(pharmacy):
    """No drawer open is not an error: the sale is paid, nothing is booked."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)
    sale_response = staff.post("/api/pharmacy/sales/", {
        "payment_method": "cash",
        "items": [{"item": item.id, "quantity": 2}],
    }, format="json")
    sale = Sale.all_objects.get(pk=sale_response.json()["id"])
    paid = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "25.00"}, format="json")
    assert paid.status_code == 200, paid.content
    sale.refresh_from_db()
    assert sale.status == Sale.Status.PAID
    assert SalePayment.all_objects.get(sale=sale).till_session_id is None


def test_payment_method_decides_what_reaches_the_drawer(pharmacy):
    """Half on card, half in cash: only the cash half is in the drawer."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)
    till_id = staff.post("/api/pharmacy/till-sessions/",
                         {"opening_float": "1000.00"}, format="json").json()["id"]

    sale = Sale.all_objects.get(pk=staff.post("/api/pharmacy/sales/", {
        "payment_method": "card",
        "items": [{"item": item.id, "quantity": 8}],
    }, format="json").json()["id"])
    assert sale.total == Decimal("100.00")  # 8 x 12.50

    # The card terminal takes 60.00; the rest is settled in notes.
    card = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "60.00"}, format="json")
    assert card.status_code == 200, card.content
    cash = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "40.00", "method": "cash"}, format="json")
    assert cash.status_code == 200, cash.content

    sale.refresh_from_db()
    assert sale.status == Sale.Status.PAID
    methods = [p.method for p in SalePayment.all_objects.filter(sale=sale)]
    assert methods == ["card", "cash"]

    till = TillSession.all_objects.get(pk=till_id)
    assert till.cash_in == Decimal("40.00")  # the card leg never touched it
    assert till.expected_amount == Decimal("1040.00")


def test_insured_copayment_in_cash_reaches_the_drawer(pharmacy):
    """An HMO sale is not a cash sale, but its co-payment is taken in notes."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    staff = _client(pharmacy["staff"], tenant)
    patient = Patient.all_objects.create(tenant=tenant, first_name="Uche",
                                         last_name="Nwosu")
    hmo = HMO.all_objects.create(tenant=tenant, name="Hygeia",
                                 coverage_percent=Decimal("80.00"))
    HmoEnrollment.all_objects.create(tenant=tenant, patient=patient, hmo=hmo,
                                     member_number="HY-9")
    till_id = staff.post("/api/pharmacy/till-sessions/",
                         {"opening_float": "2000.00"}, format="json").json()["id"]

    sale = Sale.all_objects.get(pk=staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "items": [{"item": item.id, "quantity": 8}],
    }, format="json").json()["id"])
    assert sale.patient_payable == Decimal("20.00")  # 20% of 100.00

    paid = staff.post(f"/api/pharmacy/sales/{sale.pk}/pay/",
                      {"amount": "20.00"}, format="json")
    assert paid.status_code == 200, paid.content
    payment = SalePayment.all_objects.get(sale=sale)
    assert (payment.method, payment.till_session_id) == ("cash", till_id)
    assert TillSession.all_objects.get(pk=till_id).cash_in == Decimal("20.00")


def _scheme(tenant, patient, **hmo_kwargs):
    """An insurer and one member's card on it, for the cover tests below."""
    hmo = HMO.all_objects.create(tenant=tenant, name="Leadway", **hmo_kwargs)
    enrollment = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=hmo, member_number="LW-1"
    )
    return hmo, enrollment


def _insurer_seat(tenant, hmo, phone="08030000777"):
    """A seat that signs in to the pharmacy and answers for one scheme only."""
    return User.objects.create_user(phone=phone, password="x", tenant=tenant,
                                    role=Role.HMO, hmo=hmo, username="insurer")


def test_tariff_caps_what_the_scheme_pays_for_a_line(pharmacy):
    """A drug priced above the scheme's tariff is covered only to the tariff.

    The pharmacy still charges its own price; the excess falls to the patient,
    and the two sides add back to the bill.
    """
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Uche",
                                         last_name="Obi")
    hmo, enrollment = _scheme(tenant, patient,
                              coverage_percent=Decimal("100.00"))
    # Shelf price is 12.50; the contract prices this drug at 10.00 a unit.
    HmoItemRule.all_objects.create(tenant=tenant, hmo=hmo, item=item,
                                   coverage_percent=Decimal("100.00"),
                                   tariff=Decimal("10.00"))

    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 4}],
    }, format="json")
    assert response.status_code == 201, response.content

    sale = Sale.all_objects.get(pk=response.json()["id"])
    assert sale.total == Decimal("50.00")          # 4 x 12.50, what was charged
    assert sale.hmo_payable == Decimal("40.00")    # 4 x 10.00, what was agreed
    assert sale.patient_payable == Decimal("10.00")


def test_tariff_above_the_shelf_price_never_bills_more_than_charged(pharmacy):
    """A generous tariff is a ceiling, not a floor: the bill is still the bill."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ngozi",
                                         last_name="Eze")
    hmo, enrollment = _scheme(tenant, patient,
                              coverage_percent=Decimal("100.00"))
    HmoItemRule.all_objects.create(tenant=tenant, hmo=hmo, item=item,
                                   coverage_percent=Decimal("100.00"),
                                   tariff=Decimal("99.00"))

    response = _client(pharmacy["staff"], tenant).post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 2}],
    }, format="json")
    sale = Sale.all_objects.get(pk=response.json()["id"])
    assert sale.hmo_payable == Decimal("25.00")
    assert sale.patient_payable == Decimal("0.00")


def test_insurer_keeps_its_own_price_list(pharmacy):
    """The scheme adds a drug, moves its tariff, and drops it again."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ada",
                                         last_name="Nwosu")
    hmo, _ = _scheme(tenant, patient, coverage_percent=Decimal("80.00"))
    insurer = _client(_insurer_seat(tenant, hmo), tenant)

    created = insurer.post("/api/pharmacy/item-rules/", {
        "hmo": hmo.id, "item": item.id, "coverage_percent": "60.00",
        "tariff": "10.00",
    }, format="json")
    assert created.status_code == 201, created.content
    rule_id = created.json()["id"]
    # The shelf price rides along, so a tariff is set against a real price.
    assert created.json()["item_price"] == "12.50"

    moved = insurer.patch("/api/pharmacy/item-rules/%s/" % rule_id,
                          {"tariff": "11.00"}, format="json")
    assert moved.status_code == 200, moved.content
    assert HmoItemRule.all_objects.get(pk=rule_id).tariff == Decimal("11.00")

    dropped = insurer.delete("/api/pharmacy/item-rules/%s/" % rule_id)
    assert dropped.status_code == 204
    assert not HmoItemRule.all_objects.filter(pk=rule_id).exists()


def test_insurer_cannot_price_another_scheme(pharmacy):
    """Two schemes on one pharmacy: neither reads or writes the other's list."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Sade",
                                         last_name="Bello")
    mine, _ = _scheme(tenant, patient, coverage_percent=Decimal("80.00"))
    theirs = HMO.all_objects.create(tenant=tenant, name="Hygeia")
    other_rule = HmoItemRule.all_objects.create(
        tenant=tenant, hmo=theirs, item=item, coverage_percent=Decimal("50.00")
    )
    insurer = _client(_insurer_seat(tenant, mine), tenant)

    filed = insurer.post("/api/pharmacy/item-rules/", {
        "hmo": theirs.id, "item": item.id, "coverage_percent": "100.00",
    }, format="json")
    assert filed.status_code == 400, filed.content
    assert "own scheme" in str(filed.json()["errors"]["hmo"])

    # Not even visible, so the edit is a 404 rather than a 403.
    assert insurer.patch("/api/pharmacy/item-rules/%s/" % other_rule.id,
                         {"coverage_percent": "100.00"},
                         format="json").status_code == 404
    assert insurer.get("/api/pharmacy/item-rules/").json()["results"] == []


def test_pharmacist_reads_the_price_list_but_never_writes_it(pharmacy):
    """What a sale was covered at is not a dispensing mistake's way out."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Leadway")
    rule = HmoItemRule.all_objects.create(
        tenant=tenant, hmo=hmo, item=item, coverage_percent=Decimal("50.00")
    )
    counter = _client(pharmacy["staff"], tenant)

    assert counter.get("/api/pharmacy/item-rules/").status_code == 200
    assert counter.patch("/api/pharmacy/item-rules/%s/" % rule.id,
                         {"coverage_percent": "100.00"},
                         format="json").status_code == 403
    assert counter.delete("/api/pharmacy/item-rules/%s/" % rule.id).status_code == 403


def test_a_price_list_change_notifies_the_counter(pharmacy):
    """The counter prices sales off these rows, so it hears about a move.

    The insurer who typed it is left out; the pharmacy's admin and pharmacist
    are told, and the change is on the audit trail either way.
    """
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Leadway")
    seat = _insurer_seat(tenant, hmo)

    created = _client(seat, tenant).post("/api/pharmacy/item-rules/", {
        "hmo": hmo.id, "item": item.id, "coverage_percent": "60.00",
        "tariff": "10.00",
    }, format="json")
    assert created.status_code == 201, created.content

    told = Notification.all_objects.filter(tenant=tenant)
    assert {n.user_id for n in told} == {pharmacy["admin"].id, pharmacy["staff"].id}
    assert "Leadway price list added" in told[0].title
    assert "60.00% up to 10.00 a unit" in told[0].message

    trail = AuditLog.all_objects.filter(
        content_type=ContentType.objects.get_for_model(HmoItemRule)
    )
    assert [(l.to_status, l.user_id) for l in trail] == [("added", seat.id)]

    # Dropping the row says so before it goes, while the drug still has a name.
    _client(seat, tenant).delete(
        "/api/pharmacy/item-rules/%s/" % created.json()["id"])
    assert "off the list" in told.order_by("-id")[0].message


def test_insurer_reads_the_drugs_it_can_price_without_the_cost_prices(pharmacy):
    """An insurer names the drugs to price; margins stay the pharmacy's own."""
    tenant = pharmacy["tenant"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Leadway")
    insurer = _client(_insurer_seat(tenant, hmo), tenant)

    rows = insurer.get("/api/pharmacy/item-rules/items/").json()
    assert rows == [{"id": pharmacy["item"].id, "name": "Paracetamol 500mg",
                     "unit_price": 12.5}]
    # The full item list, cost prices and all, is still staff-only.
    assert insurer.get("/api/pharmacy/items/").status_code == 403


def test_the_insurer_clears_its_own_badge_and_nobody_else_s(pharmacy):
    """A scheme is told when the pharmacy keeps its list, so it can mark it
    read - its own row only, and the flag only."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Leadway")
    seat = _insurer_seat(tenant, hmo)
    insurer = _client(seat, tenant)
    _client(pharmacy["admin"], tenant).post("/api/pharmacy/item-rules/", {
        "hmo": hmo.id, "item": item.id, "coverage_percent": "60.00",
    }, format="json")

    mine = Notification.all_objects.get(user=seat)
    theirs = Notification.all_objects.filter(user=pharmacy["staff"]).latest("id")

    read = insurer.patch("/api/pos/notifications/%s/" % mine.id,
                         {"is_read": True, "title": "rewritten"}, format="json")
    assert read.status_code == 200, read.content
    mine.refresh_from_db()
    assert mine.is_read is True
    # Only the flag: what the notification said still says it.
    assert mine.title != "rewritten"

    # The counter's bell is not the insurer's to clear.
    assert insurer.patch("/api/pos/notifications/%s/" % theirs.id,
                         {"is_read": True}, format="json").status_code == 404
    insurer.post("/api/pos/notifications/read-all/")
    theirs.refresh_from_db()
    assert theirs.is_read is False
    assert insurer.get("/api/pos/notifications/",
                       {"is_read": "false"}).json()["count"] == 0


def test_per_drug_rules_price_each_line_and_zero_excludes(pharmacy):
    """A scheme that pays 80% by default, half for a branded alternative and
    nothing for vitamins, is billed line by line - not 80% of the whole bill."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    vitamin = StockItem.all_objects.create(
        tenant=tenant, name="Vitamin C", sku="VITC", unit="tablet",
        cost_price=Decimal("40.00"), unit_price=Decimal("100.00"),
    )
    branded = StockItem.all_objects.create(
        tenant=tenant, name="Panadol Extra", sku="PANEX", unit="tablet",
        cost_price=Decimal("30.00"), unit_price=Decimal("50.00"),
    )
    receive_stock(vitamin, 10, batch_number="V-1")
    receive_stock(branded, 10, batch_number="P-1")
    patient = Patient.all_objects.create(tenant=tenant, first_name="Bola",
                                         last_name="Ade")
    hmo, enrollment = _scheme(tenant, patient,
                              coverage_percent=Decimal("80.00"))
    HmoItemRule.all_objects.create(tenant=tenant, hmo=hmo, item=vitamin,
                                   coverage_percent=Decimal("0.00"),
                                   note="Supplements are not covered.")
    HmoItemRule.all_objects.create(tenant=tenant, hmo=hmo, item=branded,
                                   coverage_percent=Decimal("50.00"))

    staff = _client(pharmacy["staff"], tenant)
    response = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 10},
                  {"item": vitamin.id, "quantity": 2},
                  {"item": branded.id, "quantity": 4}],
    }, format="json")
    assert response.status_code == 201, response.content
    sale = Sale.all_objects.get(pk=response.json()["id"])
    # 125.00 at 80% + 200.00 at nothing + 200.00 at half.
    assert sale.total == Decimal("525.00")
    assert sale.hmo_payable == Decimal("200.00")
    assert sale.patient_payable == Decimal("325.00")
    assert sale.patient_payable + sale.hmo_payable == sale.total
    assert Claim.all_objects.get(sale=sale).amount == Decimal("200.00")


def test_annual_limit_caps_cover_and_a_cancelled_claim_gives_it_back(pharmacy):
    """A member with 50.00 of benefit left gets 50.00 of a fully covered bill,
    and the rest is theirs. Cancelling the claim frees the benefit again."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Chidi",
                                         last_name="Eze")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"))
    enrollment.annual_limit = Decimal("50.00")
    enrollment.save(update_fields=["annual_limit"])

    staff = _client(pharmacy["staff"], tenant)
    response = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 10}],
    }, format="json")
    assert response.status_code == 201, response.content
    sale = Sale.all_objects.get(pk=response.json()["id"])
    assert sale.total == Decimal("125.00")
    assert sale.hmo_payable == Decimal("50.00")
    assert sale.patient_payable == Decimal("75.00")
    assert enrollment.remaining_benefit() == Decimal("0.00")

    # The next sale gets no cover at all: the year's benefit is spent.
    again = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 4}],
    }, format="json")
    assert again.status_code == 201, again.content
    second = Sale.all_objects.get(pk=again.json()["id"])
    assert second.hmo_payable == Decimal("0.00")
    assert second.patient_payable == second.total
    # Nothing to bill, so no claim was raised.
    assert not Claim.all_objects.filter(sale=second).exists()

    claim = Claim.all_objects.get(sale=sale)
    admin = _client(pharmacy["admin"], tenant)
    # Writing off insured money is the admin's call, not the counter's.
    assert staff.post(f"/api/pharmacy/claims/{claim.pk}/cancel/", {},
                      format="json").status_code == 403
    cancelled = admin.post(f"/api/pharmacy/claims/{claim.pk}/cancel/",
                           {"reason": "Billed in error."}, format="json")
    assert cancelled.status_code == 200, cancelled.content
    claim.refresh_from_db()
    assert claim.status == Claim.Status.CANCELLED
    assert enrollment.remaining_benefit() == Decimal("50.00")
    # A cancelled claim is finished: it cannot be sent to the insurer after all.
    assert admin.post(f"/api/pharmacy/claims/{claim.pk}/submit/", {},
                      format="json").status_code == 400


def test_high_value_cover_needs_a_recorded_authorisation(pharmacy):
    """Above the insurer's threshold the sale is refused until an approved
    request covers it - and the refused basket puts its stock back."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ngozi",
                                         last_name="Udo")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)
    basket = {"patient": patient.id, "payment_method": "hmo",
              "enrollment": enrollment.id,
              "items": [{"item": item.id, "quantity": 10}]}

    refused = staff.post("/api/pharmacy/sales/", basket, format="json")
    assert refused.status_code == 400
    assert "authorization" in refused.content.decode()
    item.refresh_from_db()
    assert item.quantity_on_hand == 80
    assert not Sale.all_objects.filter(patient=patient).exists()

    # The counter asks the insurer; the answer is the admin's to record.
    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id, "amount": "125.00",
        "notes": "Ten tablets, chronic patient.",
    }, format="json")
    assert asked.status_code == 201, asked.content
    auth = PreAuthorization.all_objects.get(pk=asked.json()["id"])
    assert (auth.status, auth.hmo_id) == (PreAuthorization.Status.REQUESTED,
                                          enrollment.hmo_id)
    assert staff.post(f"/api/pharmacy/pre-authorizations/{auth.pk}/approve/",
                      {"code": "AUTH-77"}, format="json").status_code == 403

    # An unapproved request is no clearance at all.
    assert staff.post("/api/pharmacy/sales/", dict(basket, authorization=auth.pk),
                      format="json").status_code == 400

    # The insurer stands behind less than was asked, so the sale is still short.
    admin.post(f"/api/pharmacy/pre-authorizations/{auth.pk}/approve/",
               {"code": "AUTH-77", "amount": "100.00"}, format="json")
    short = staff.post("/api/pharmacy/sales/", dict(basket, authorization=auth.pk),
                       format="json")
    assert short.status_code == 400
    assert "authorised 100.00" in short.content.decode()

    # Cleared for the full amount, the sale goes through and spends the approval.
    full = PreAuthorization.all_objects.create(
        tenant=tenant, enrollment=enrollment, hmo=enrollment.hmo,
        amount=Decimal("125.00"),
    )
    full.approve(code="AUTH-88", amount=Decimal("125.00"))
    allowed = staff.post("/api/pharmacy/sales/",
                         dict(basket, authorization=full.pk), format="json")
    assert allowed.status_code == 201, allowed.content
    sale = Sale.all_objects.get(pk=allowed.json()["id"])
    assert sale.hmo_payable == Decimal("125.00")
    full.refresh_from_db()
    assert full.status == PreAuthorization.Status.USED
    # The code travels onto the claim - the insurer quotes it back.
    claim = Claim.all_objects.get(sale=sale)
    assert staff.get(f"/api/pharmacy/claims/{claim.pk}/").json()[
        "authorization_code"] == "AUTH-88"

    # One approval, one sale: it cannot clear a second basket.
    assert staff.post("/api/pharmacy/sales/", dict(basket, authorization=full.pk),
                      format="json").status_code == 400

    # A bill under the threshold needs no clearance.
    small = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 4}],
    }, format="json")
    assert small.status_code == 201, small.content


def test_a_lapsed_authorisation_does_not_clear_a_sale(pharmacy):
    """An approval given for last month is not a clearance today."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Sade",
                                         last_name="Lawal")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    auth = PreAuthorization.all_objects.create(
        tenant=tenant, enrollment=enrollment, hmo=enrollment.hmo,
        amount=Decimal("125.00"),
    )
    auth.approve(code="OLD-1", amount=Decimal("125.00"),
                 expires_on=timezone.localdate() - timedelta(days=1))
    assert auth.is_usable is False

    staff = _client(pharmacy["staff"], tenant)
    stale = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id, "authorization": auth.pk,
        "items": [{"item": item.id, "quantity": 10}],
    }, format="json")
    assert stale.status_code == 400
    assert "expired" in stale.content.decode()
    item.refresh_from_db()
    assert item.quantity_on_hand == 80


def test_the_insurer_answers_each_ordered_medication_on_its_own(pharmacy):
    """The pharmacy asks about two drugs, the HMO clears one and refuses the
    other, and the counter dispenses exactly what came back cleared."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    vitamin = StockItem.all_objects.create(
        tenant=tenant, name="Vitamin C", sku="VITC", unit="tablet",
        cost_price=Decimal("40.00"), unit_price=Decimal("100.00"),
    )
    receive_stock(vitamin, 20, batch_number="V-1", cost_price=Decimal("40.00"))
    patient = Patient.all_objects.create(tenant=tenant, first_name="Bola",
                                         last_name="Eze")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)

    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id,
        "items": [
            {"item": item.id, "quantity": 10, "amount": "125.00"},
            {"item": vitamin.id, "quantity": 2, "amount": "200.00"},
        ],
    }, format="json")
    assert asked.status_code == 201, asked.content
    auth = PreAuthorization.all_objects.get(pk=asked.json()["id"])
    # The request is worth what the medications on it add up to.
    assert auth.amount == Decimal("325.00")
    para_line, vit_line = PreAuthorizationItem.all_objects.filter(
        authorization=auth).order_by("id")

    # Only the admin records what the insurer said about a medication.
    assert staff.post(
        f"/api/pharmacy/pre-authorization-items/{para_line.pk}/approve/", {},
        format="json").status_code == 403

    # One drug decided leaves the request open — a half-answer clears nothing.
    admin.post(f"/api/pharmacy/pre-authorization-items/{para_line.pk}/approve/",
               {"amount": "125.00"}, format="json")
    auth.refresh_from_db()
    assert auth.status == PreAuthorization.Status.REQUESTED

    declined = admin.post(
        f"/api/pharmacy/pre-authorization-items/{vit_line.pk}/decline/",
        {"reason": "Supplements are not covered."}, format="json")
    assert declined.status_code == 200, declined.content
    # Answered in full, the request settles at what was actually cleared.
    auth.refresh_from_db()
    assert (auth.status, auth.amount_approved) == (PreAuthorization.Status.APPROVED,
                                                   Decimal("125.00"))
    # And the same answer cannot be given twice.
    assert admin.post(
        f"/api/pharmacy/pre-authorization-items/{vit_line.pk}/approve/", {},
        format="json").status_code == 400

    basket = {"patient": patient.id, "payment_method": "hmo",
              "enrollment": enrollment.id, "authorization": auth.pk}

    # The refused drug is refused at the till, and its stock goes back.
    refused = staff.post("/api/pharmacy/sales/", dict(basket, items=[
        {"item": item.id, "quantity": 10}, {"item": vitamin.id, "quantity": 2},
    ]), format="json")
    assert refused.status_code == 400
    assert "Vitamin C" in refused.content.decode()
    vitamin.refresh_from_db()
    assert vitamin.quantity_on_hand == 20

    # The cleared drug alone goes out, on the cover the insurer gave.
    allowed = staff.post("/api/pharmacy/sales/", dict(basket, items=[
        {"item": item.id, "quantity": 10},
    ]), format="json")
    assert allowed.status_code == 201, allowed.content
    sale = Sale.all_objects.get(pk=allowed.json()["id"])
    assert sale.hmo_payable == Decimal("125.00")


def test_the_insurer_clears_part_of_a_quantity(pharmacy):
    """The pharmacy asks for 30 tablets, the HMO stands behind 20, and the till
    refuses the 30 and passes the 20 - with the requester told the answer."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ada",
                                         last_name="Nwosu")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)

    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 30, "amount": "375.00"}],
    }, format="json")
    assert asked.status_code == 201, asked.content
    auth = PreAuthorization.all_objects.get(pk=asked.json()["id"])
    line = PreAuthorizationItem.all_objects.get(authorization=auth)

    # More than was asked for is not an answer the insurer can give.
    assert admin.post(
        f"/api/pharmacy/pre-authorization-items/{line.pk}/approve/",
        {"quantity": 40}, format="json").status_code == 400

    cleared = admin.post(
        f"/api/pharmacy/pre-authorization-items/{line.pk}/approve/",
        {"quantity": 20}, format="json")
    assert cleared.status_code == 200, cleared.content
    line.refresh_from_db()
    auth.refresh_from_db()
    # A cut quantity cuts the bill with it, pro rata.
    assert (line.quantity_approved, line.amount_approved) == (20, Decimal("250.00"))
    assert (auth.status, auth.amount_approved) == (PreAuthorization.Status.APPROVED,
                                                   Decimal("250.00"))

    # Whoever raised the request hears the answer without reloading it.
    told = Notification.all_objects.filter(user=pharmacy["staff"]).latest("id")
    assert auth.reference in told.title and "authorised" in told.title

    basket = {"patient": patient.id, "payment_method": "hmo",
              "enrollment": enrollment.id, "authorization": auth.pk}
    over = staff.post("/api/pharmacy/sales/",
                      dict(basket, items=[{"item": item.id, "quantity": 30}]),
                      format="json")
    assert over.status_code == 400
    assert "20 of 30 cleared" in over.content.decode()

    within = staff.post("/api/pharmacy/sales/",
                        dict(basket, items=[{"item": item.id, "quantity": 20}]),
                        format="json")
    assert within.status_code == 201, within.content
    assert Sale.all_objects.get(pk=within.json()["id"]).hmo_payable == Decimal("250.00")


def test_a_withdrawn_request_is_told_back_to_whoever_raised_it(pharmacy):
    """The counter withdraws its own request; the notification is what the bell
    counts, so it is raised for the sale that never happened too."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ife",
                                         last_name="Okoro")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)
    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 10, "amount": "125.00"}],
    }, format="json")
    auth = PreAuthorization.all_objects.get(pk=asked.json()["id"])

    gone = staff.post(f"/api/pharmacy/pre-authorizations/{auth.pk}/cancel/",
                      {"reason": "The patient left."}, format="json")
    assert gone.status_code == 200, gone.content

    told = Notification.all_objects.filter(user=pharmacy["staff"]).latest("id")
    assert told.title == f"{auth.reference} withdrawn"
    assert told.message == "The patient left."
    # And it is the requester's own bell, not the whole counter's.
    unread = staff.get("/api/pos/notifications/", {"is_read": "false"})
    assert unread.status_code == 200, unread.content
    assert unread.json()["count"] == 1


def test_a_wrong_answer_is_reopened_and_recorded_again(pharmacy):
    """An amount typed wrong is withdrawn and recorded properly - until the
    clearance has been spent on a sale, after which it stands."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Chidi",
                                         last_name="Obi")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)

    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id,
        "items": [{"item": item.id, "quantity": 10, "amount": "125.00"}],
    }, format="json")
    assert asked.status_code == 201, asked.content
    auth = PreAuthorization.all_objects.get(pk=asked.json()["id"])
    line = PreAuthorizationItem.all_objects.get(authorization=auth)

    # The insurer cleared 5, the admin typed 10. The one line settles the
    # request, so the wrong figure is now the request's figure too.
    admin.post(f"/api/pharmacy/pre-authorization-items/{line.pk}/approve/",
               {"quantity": 10}, format="json")
    auth.refresh_from_db()
    assert (auth.status, auth.amount_approved) == (PreAuthorization.Status.APPROVED,
                                                   Decimal("125.00"))

    # Counter staff cannot unpick an insurer's answer any more than they can
    # record one.
    assert staff.post(
        f"/api/pharmacy/pre-authorization-items/{line.pk}/reopen/", {},
        format="json").status_code == 403

    reopened = admin.post(
        f"/api/pharmacy/pre-authorization-items/{line.pk}/reopen/",
        {"reason": "Typed 10, they cleared 5."}, format="json")
    assert reopened.status_code == 200, reopened.content

    # Who undid what is answerable afterwards: the medication and the request
    # it settled both name the admin who withdrew the answer.
    trail = admin.get(f"/api/pharmacy/pre-authorizations/{auth.pk}/history/")
    assert trail.status_code == 200, trail.content
    rows = trail.json()
    assert len(rows) == 2
    assert {r["user"] for r in rows} == {pharmacy["admin"].pk}
    assert all(r["to_status"] == "requested" for r in rows)
    assert any("Typed 10, they cleared 5." in r["note"] for r in rows)
    line.refresh_from_db()
    auth.refresh_from_db()
    assert (line.status, line.quantity_approved) == (
        PreAuthorizationItem.Status.REQUESTED, 0)
    # The counter reads how often an answer here was withdrawn without going
    # near the trail.
    assert auth.reopened_count == 1
    # The request goes back with it: a corrected line under a stale total
    # would clear a sale for money nobody agreed to.
    assert (auth.status, auth.amount_approved) == (PreAuthorization.Status.REQUESTED,
                                                   Decimal("0.00"))

    right = admin.post(f"/api/pharmacy/pre-authorization-items/{line.pk}/approve/",
                       {"quantity": 5}, format="json")
    assert right.status_code == 200, right.content
    auth.refresh_from_db()
    assert (auth.status, auth.amount_approved) == (PreAuthorization.Status.APPROVED,
                                                   Decimal("62.50"))

    # Spent on a sale, the answer is history - the drugs left the shelf on it.
    sold = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id, "authorization": auth.pk,
        "items": [{"item": item.id, "quantity": 5}],
    }, format="json")
    assert sold.status_code == 201, sold.content
    auth.refresh_from_db()
    assert auth.status == PreAuthorization.Status.USED
    stuck = admin.post(
        f"/api/pharmacy/pre-authorization-items/{line.pk}/reopen/", {},
        format="json")
    assert stuck.status_code == 400
    assert "new request" in stuck.content.decode()


def test_a_lump_sum_answer_is_reopened_too(pharmacy):
    """A request with no medications on it is answered as a whole, and that
    answer is withdrawn the same way."""
    tenant = pharmacy["tenant"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Ngozi",
                                         last_name="Uche")
    _hmo, enrollment = _scheme(tenant, patient,
                               coverage_percent=Decimal("100.00"),
                               preauth_threshold=Decimal("100.00"))
    admin = _client(pharmacy["admin"], tenant)
    auth = PreAuthorization.all_objects.create(
        tenant=tenant, enrollment=enrollment, hmo=enrollment.hmo,
        amount=Decimal("500.00"), requested_by=pharmacy["staff"],
    )
    auth.approve(code="WRONG-1", amount=Decimal("500.00"))

    undone = admin.post(f"/api/pharmacy/pre-authorizations/{auth.pk}/reopen/",
                        {"reason": "Wrong scheme quoted."}, format="json")
    assert undone.status_code == 200, undone.content
    auth.refresh_from_db()
    assert (auth.status, auth.amount_approved, auth.code) == (
        PreAuthorization.Status.REQUESTED, Decimal("0.00"), "")
    # Whoever raised it hears that the answer they were given no longer stands.
    told = Notification.all_objects.filter(user=pharmacy["staff"]).latest("id")
    assert "reopened" in told.title
    # The withdrawn amount is on the trail, which is the whole point of it -
    # the request itself no longer carries the figure that was erased.
    logged = admin.get(f"/api/pharmacy/pre-authorizations/{auth.pk}/history/")
    assert logged.status_code == 200, logged.content
    assert logged.json()[0]["from_status"] == "approved"
    assert "500.00" in logged.json()[0]["note"]
    assert auth.reopened_count == 1

    auth.approve(code="RIGHT-1", amount=Decimal("400.00"))
    auth.mark_used()
    # A spent clearance is not unpicked, and neither is a withdrawn request.
    assert admin.post(f"/api/pharmacy/pre-authorizations/{auth.pk}/reopen/", {},
                      format="json").status_code == 400


def test_the_insurer_seat_answers_its_own_requests_and_claims(pharmacy):
    """The scheme's own seat clears a request and approves a claim itself —
    the admin is only a stand-in for an insurer with no seat. It still answers
    for its own scheme alone, and the pharmacy's money stays the admin's."""
    tenant, item = pharmacy["tenant"], pharmacy["item"]
    patient = Patient.all_objects.create(tenant=tenant, first_name="Amaka",
                                         last_name="Obi")
    hmo, enrollment = _scheme(tenant, patient,
                              coverage_percent=Decimal("100.00"),
                              preauth_threshold=Decimal("100.00"))
    other = HMO.all_objects.create(tenant=tenant, name="Hygeia")
    other_card = HmoEnrollment.all_objects.create(
        tenant=tenant, patient=patient, hmo=other, member_number="HY-1")
    staff = _client(pharmacy["staff"], tenant)
    insurer = _client(_insurer_seat(tenant, hmo), tenant)

    asked = staff.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id, "amount": "125.00",
    }, format="json")
    assert asked.status_code == 201, asked.content
    auth_id = asked.json()["id"]
    theirs = PreAuthorization.all_objects.create(
        tenant=tenant, hmo=other, enrollment=other_card, amount=Decimal("90.00"))

    # Another scheme's request is not even visible to this seat.
    assert insurer.post(f"/api/pharmacy/pre-authorizations/{theirs.pk}/approve/",
                        {}, format="json").status_code == 404
    # Raising or withdrawing a request stays the pharmacy's.
    assert insurer.post("/api/pharmacy/pre-authorizations/", {
        "enrollment": enrollment.id, "amount": "10.00"}, format="json"
    ).status_code == 403
    assert insurer.post(f"/api/pharmacy/pre-authorizations/{auth_id}/cancel/",
                        {}, format="json").status_code == 403

    cleared = insurer.post(f"/api/pharmacy/pre-authorizations/{auth_id}/approve/",
                           {"code": "LW-OK-1", "amount": "100.00"}, format="json")
    assert cleared.status_code == 200, cleared.content
    auth = PreAuthorization.all_objects.get(pk=auth_id)
    assert (auth.status, auth.code, auth.amount_approved) == (
        PreAuthorization.Status.APPROVED, "LW-OK-1", Decimal("100.00"))

    # The clearance is spent on the sale, and the claim it raises goes back to
    # the same seat to approve.
    sold = staff.post("/api/pharmacy/sales/", {
        "patient": patient.id, "payment_method": "hmo",
        "enrollment": enrollment.id, "authorization": auth_id,
        "items": [{"item": item.id, "quantity": 8}],
    }, format="json")
    assert sold.status_code == 201, sold.content
    claim = Claim.all_objects.get(sale_id=sold.json()["id"])
    staff.post(f"/api/pharmacy/claims/{claim.pk}/submit/", {}, format="json")
    assert insurer.post(f"/api/pharmacy/claims/{claim.pk}/approve/",
                        {"amount": "80.00"}, format="json").status_code == 200
    claim.refresh_from_db()
    assert claim.amount_approved == Decimal("80.00")
    # Banking the remittance is the pharmacy's, not the insurer's.
    assert insurer.post(f"/api/pharmacy/claims/{claim.pk}/pay/",
                        {"amount": "80.00"}, format="json").status_code == 403
