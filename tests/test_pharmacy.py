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

from apps.accounts.models import Role, User
from apps.patients.models import Patient
from apps.pharmacy.models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
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


def test_claim_batch_submits_together_and_pays_per_claim(pharmacy):
    """One envelope out, one remittance back, allocated claim by claim."""
    tenant = pharmacy["tenant"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Hygeia",
                                 coverage_percent=Decimal("100.00"))
    first = _hmo_sale(pharmacy, hmo, 4, "HY-1")    # 50.00
    second = _hmo_sale(pharmacy, hmo, 8, "HY-2")   # 100.00
    # A claim for another insurer must not be swept into this batch.
    other_hmo = HMO.all_objects.create(tenant=tenant, name="Reliance")
    outsider = _hmo_sale(pharmacy, other_hmo, 2, "RL-1")

    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)
    today = timezone.localdate()
    created = staff.post("/api/pharmacy/claim-batches/", {
        "hmo": hmo.id, "period_start": str(today - timedelta(days=30)),
        "period_end": str(today),
    }, format="json")
    assert created.status_code == 201, created.content
    batch = ClaimBatch.all_objects.get(pk=created.json()["id"])
    assert batch.totals["claims"] == 2
    assert batch.totals["claimed"] == Decimal("150.00")
    outsider.refresh_from_db()
    assert outsider.batch_id is None

    assert staff.post(f"/api/pharmacy/claim-batches/{batch.pk}/submit/", {},
                      format="json").status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    batch.refresh_from_db()
    assert first.status == second.status == Claim.Status.SUBMITTED
    assert batch.status == ClaimBatch.Status.SUBMITTED

    # Staff send the schedule; only the admin settles it.
    assert staff.post(f"/api/pharmacy/claim-batches/{batch.pk}/approve/", {},
                      format="json").status_code == 403
    assert admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/approve/", {},
                      format="json").status_code == 200
    batch.refresh_from_db()
    assert batch.status == ClaimBatch.Status.APPROVED
    assert batch.totals["outstanding"] == Decimal("150.00")

    # A remittance is spread oldest claim first: 60 settles the 50 claim and
    # leaves 10 against the 100 one.
    assert admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/pay/",
                      {"amount": "60.00"}, format="json").status_code == 200
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, first.amount_paid) == (Claim.Status.PAID,
                                                 Decimal("50.00"))
    assert (second.status, second.amount_paid) == (Claim.Status.APPROVED,
                                                   Decimal("10.00"))

    # Money the batch is not owed has nowhere to go.
    too_much = admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/pay/",
                          {"amount": "500.00"}, format="json")
    assert too_much.status_code == 400
    assert "only owed" in too_much.json()["message"]

    assert admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/pay/",
                      {"amount": "90.00"}, format="json").status_code == 200
    batch.refresh_from_db()
    second.refresh_from_db()
    assert second.status == Claim.Status.PAID
    assert batch.status == ClaimBatch.Status.PAID
    assert batch.totals["outstanding"] == Decimal("0.00")


def test_cancelled_batch_releases_its_claims(pharmacy):
    tenant = pharmacy["tenant"]
    hmo = HMO.all_objects.create(tenant=tenant, name="AXA")
    claim = _hmo_sale(pharmacy, hmo, 2, "AX-1")
    staff = _client(pharmacy["staff"], tenant)
    batch = ClaimBatch.all_objects.get(pk=staff.post("/api/pharmacy/claim-batches/",
                                                     {"hmo": hmo.id},
                                                     format="json").json()["id"])
    claim.refresh_from_db()
    assert claim.batch_id == batch.pk

    assert staff.post(f"/api/pharmacy/claim-batches/{batch.pk}/cancel/", {},
                      format="json").status_code == 200
    claim.refresh_from_db()
    batch.refresh_from_db()
    # The claim is loose again and can be sent on its own or in another month.
    assert claim.batch_id is None and claim.status == Claim.Status.DRAFT
    assert batch.status == ClaimBatch.Status.CANCELLED


def test_batch_of_cancelled_claims_will_not_submit(pharmacy):
    """Nothing is left to send once every collected claim was cancelled with its
    sale, so the schedule is refused rather than going out empty."""
    tenant = pharmacy["tenant"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Hygeia")
    claim = _hmo_sale(pharmacy, hmo, 2, "HY-1")
    staff = _client(pharmacy["staff"], tenant)
    batch = ClaimBatch.all_objects.get(pk=staff.post("/api/pharmacy/claim-batches/",
                                                     {"hmo": hmo.id},
                                                     format="json").json()["id"])
    Sale.all_objects.get(pk=claim.sale_id).cancel()

    response = staff.post(f"/api/pharmacy/claim-batches/{batch.pk}/submit/", {},
                          format="json")
    assert response.status_code == 400, response.content
    batch.refresh_from_db()
    assert batch.status == ClaimBatch.Status.DRAFT


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


def test_batch_collects_a_claim_that_was_sent_on_its_own(pharmacy):
    """An auto-submitting insurer still gets a monthly schedule: its claims are
    already with it, but the batch is what the remittance is read against."""
    tenant = pharmacy["tenant"]
    hmo = HMO.all_objects.create(tenant=tenant, name="Reliance",
                                 coverage_percent=Decimal("100.00"),
                                 auto_submit_claims=True)
    sent = _hmo_sale(pharmacy, hmo, 4, "RL-1")     # 50.00, already submitted
    assert sent.status == Claim.Status.SUBMITTED

    hmo.auto_submit_claims = False
    hmo.save(update_fields=["auto_submit_claims"])
    waiting = _hmo_sale(pharmacy, hmo, 8, "RL-2")  # 100.00, still a draft

    staff = _client(pharmacy["staff"], tenant)
    admin = _client(pharmacy["admin"], tenant)
    today = timezone.localdate()
    unbatched = [r["batch_reference"]
                 for r in staff.get("/api/pharmacy/claims/").json()["results"]]
    created = staff.post("/api/pharmacy/claim-batches/", {
        "hmo": hmo.id, "period_start": str(today - timedelta(days=30)),
        "period_end": str(today),
    }, format="json")
    assert created.status_code == 201, created.content
    batch = ClaimBatch.all_objects.get(pk=created.json()["id"])
    assert batch.totals["claims"] == 2
    assert batch.totals["claimed"] == Decimal("150.00")

    # The claim list names the schedule each claim landed on — unbatched before,
    # this batch after. That is the only place a reader can see the collection.
    assert unbatched == [None, None]
    listed = staff.get("/api/pharmacy/claims/").json()["results"]
    assert {r["batch_reference"] for r in listed} == {batch.reference}

    # Sending the schedule submits the draft and leaves the sent one alone —
    # its submitted_at is when the insurer actually got it.
    sent_at = sent.submitted_at
    assert staff.post(f"/api/pharmacy/claim-batches/{batch.pk}/submit/", {},
                      format="json").status_code == 200
    sent.refresh_from_db()
    waiting.refresh_from_db()
    assert sent.status == waiting.status == Claim.Status.SUBMITTED
    assert sent.submitted_at == sent_at

    # And the remittance settles both.
    assert admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/approve/", {},
                      format="json").status_code == 200
    assert admin.post(f"/api/pharmacy/claim-batches/{batch.pk}/pay/",
                      {"amount": "150.00"}, format="json").status_code == 200
    sent.refresh_from_db()
    assert sent.status == Claim.Status.PAID


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
