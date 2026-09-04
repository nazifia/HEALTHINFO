"""The counter features ported from PharmApp: wallet, returns, counts, transfers.

The checks that matter are the ones where a bug costs someone money or a drug:
a wallet that overdraws recording real debt rather than silently free goods, a
refund landing on the day it happened, a stocktake writing its discrepancy to
the ledger, and a transfer that can never leave units on neither shelf.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.customers.models import Customer, WalletTransaction
from apps.inventory.models import (
    OutOfStock,
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Store,
    TransferRequest,
    receive_stock,
)
from apps.pos.models import (
    ExpenseCategory,
    Expense,
    ReturnRecord,
    Sale,
    SaleItem,
    TillSession,
    record_return,
)
from apps.prescriptions.models import (
    ConsultationPayout,
    Hospital,
    Prescriber,
    PrescriberCommission,
    Prescription,
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
def counter(db_clean):
    """A tenant with staff, a retail item stocked 100 deep, and a customer."""
    tenant = Tenant.objects.create(name="Bola Pharmacy", slug="bola")
    admin = User.objects.create_user(phone="08030000301", password="x",
                                     tenant=tenant, role=Role.TENANT_ADMIN,
                                     username="counteradmin")
    staff = User.objects.create_user(phone="08030000302", password="x",
                                     tenant=tenant, role=Role.PHARMACIST,
                                     username="counterstaff")
    item = StockItem.all_objects.create(
        tenant=tenant, name="Amoxicillin 250mg", sku="AMOX250", unit="capsule",
        cost_price=Decimal("10.00"), unit_price=Decimal("25.00"),
        store=Store.RETAIL, reorder_level=10,
    )
    receive_stock(item, 100, batch_number="AM-1",
                  expiry_date=timezone.localdate() + timedelta(days=200),
                  cost_price=Decimal("10.00"))
    customer = Customer.all_objects.create(
        tenant=tenant, name="Chidi Okafor", phone="08099999999",
    )
    return {"tenant": tenant, "admin": admin, "staff": staff, "item": item,
            "customer": customer}


def _sell(counter, quantity=4, **kwargs):
    """One cash sale of ``quantity``, through the API so validation runs."""
    payload = {"items": [{"item": counter["item"].pk, "quantity": quantity}]}
    payload.update(kwargs)
    response = _client(counter["staff"], counter["tenant"]).post(
        "/api/pos/sales/", payload, format="json"
    )
    assert response.status_code == 201, response.data
    return Sale.all_objects.get(pk=response.data["id"])


# --- wallet ---------------------------------------------------------------

def test_topup_clears_debt_before_it_adds_credit(counter):
    customer = counter["customer"]
    customer.outstanding_debt = Decimal("300.00")
    customer.save(update_fields=["outstanding_debt"])

    customer.top_up(Decimal("500.00"), method="cash")
    customer.refresh_from_db()

    assert customer.outstanding_debt == Decimal("0.00")
    assert customer.wallet_balance == Decimal("200.00")
    assert WalletTransaction.all_objects.filter(
        customer=customer, txn_type="topup", method="cash"
    ).count() == 1


def test_short_wallet_dispenses_on_credit_and_stays_out_of_revenue(counter):
    """The goods have left the shelf: the shortfall is debt, not a free sale."""
    customer = counter["customer"]
    customer.top_up(Decimal("40.00"))          # bill will be 100.00
    sale = _sell(counter, quantity=4, customer=customer.pk,
                 payment_method=Sale.PaymentMethod.WALLET)

    response = _client(counter["staff"], counter["tenant"]).post(
        f"/api/pos/sales/{sale.pk}/pay-wallet/", {}, format="json"
    )
    assert response.status_code == 200, response.data
    sale.refresh_from_db()
    customer.refresh_from_db()

    assert sale.total == Decimal("100.00")
    assert sale.amount_paid == Decimal("40.00")
    assert sale.status == Sale.Status.CREDIT
    assert customer.wallet_balance == Decimal("0.00")
    assert customer.outstanding_debt == Decimal("60.00")
    # Credit is not revenue until it is paid.
    assert sale.status not in Sale.REVENUE_STATUSES


def test_a_funded_wallet_settles_the_sale_outright(counter):
    customer = counter["customer"]
    customer.top_up(Decimal("500.00"))
    sale = _sell(counter, quantity=4, customer=customer.pk,
                 payment_method=Sale.PaymentMethod.WALLET)
    sale.pay_from_wallet()
    sale.refresh_from_db()
    customer.refresh_from_db()

    assert sale.status == Sale.Status.PAID
    assert customer.wallet_balance == Decimal("400.00")
    assert customer.outstanding_debt == Decimal("0.00")


# --- returns --------------------------------------------------------------

def test_partial_return_puts_stock_back_and_refunds_to_the_wallet(counter):
    customer = counter["customer"]
    sale = _sell(counter, quantity=10, customer=customer.pk)
    line = SaleItem.all_objects.get(sale=sale)
    batch = StockBatch.all_objects.get(item=counter["item"])
    assert batch.quantity == 90

    record = record_return(line, 4, refund_method=ReturnRecord.RefundMethod.WALLET,
                           reason="Wrong strength", user=counter["staff"])

    batch.refresh_from_db()
    line.refresh_from_db()
    sale.refresh_from_db()
    customer.refresh_from_db()

    assert batch.quantity == 94
    assert line.return_quantity == 4
    assert record.amount == Decimal("100.00")     # 4 x 25.00
    assert customer.wallet_balance == Decimal("100.00")
    assert sale.status == Sale.Status.PARTIAL_RETURN
    assert StockMovement.all_objects.filter(
        sale=sale, kind=StockMovement.Kind.RETURN
    ).count() == 1


def test_returning_every_unit_marks_the_sale_returned(counter):
    sale = _sell(counter, quantity=5)
    line = SaleItem.all_objects.get(sale=sale)
    record_return(line, 5, refund_method=ReturnRecord.RefundMethod.CASH)
    sale.refresh_from_db()
    assert sale.status == Sale.Status.RETURNED


def test_more_cannot_come_back_than_went_out(counter):
    sale = _sell(counter, quantity=3)
    line = SaleItem.all_objects.get(sale=sale)
    record_return(line, 2)
    with pytest.raises(ValueError):
        record_return(line, 2)


# --- stock check ----------------------------------------------------------

def test_stock_check_writes_its_discrepancy_to_the_ledger(counter):
    """A short count is shrinkage: it is adjusted, and the ledger says by how much."""
    tenant, item = counter["tenant"], counter["item"]
    check = StockCheck.all_objects.create(tenant=tenant, store=Store.RETAIL,
                                          created_by=counter["staff"])
    line = StockCheckItem.all_objects.create(
        tenant=tenant, stock_check=check, item=item,
        expected_quantity=item.quantity_on_hand, actual_quantity=93,
    )
    assert line.discrepancy == -7
    assert line.cost_difference == Decimal("-70.00")

    check.complete(user=counter["admin"])
    line.refresh_from_db()

    assert item.quantity_on_hand == 93
    assert line.status == StockCheckItem.Status.ADJUSTED
    assert check.status == StockCheck.Status.COMPLETED
    movement = StockMovement.all_objects.get(
        item=item, kind=StockMovement.Kind.ADJUSTMENT
    )
    assert movement.quantity == -7


def test_an_uncounted_line_is_left_alone(counter):
    """Not counting something is not the same as counting zero."""
    tenant, item = counter["tenant"], counter["item"]
    check = StockCheck.all_objects.create(tenant=tenant, created_by=counter["staff"])
    StockCheckItem.all_objects.create(
        tenant=tenant, stock_check=check, item=item,
        expected_quantity=item.quantity_on_hand,
    )
    check.complete(user=counter["admin"])
    assert item.quantity_on_hand == 100


# --- transfers ------------------------------------------------------------

def test_transfer_moves_units_between_the_two_stores(counter):
    tenant, retail = counter["tenant"], counter["item"]
    wholesale = StockItem.all_objects.create(
        tenant=tenant, name="Amoxicillin 250mg (pack)", sku="AMOX250W",
        unit="pack", cost_price=Decimal("10.00"), unit_price=Decimal("22.00"),
        store=Store.WHOLESALE,
    )
    receive_stock(wholesale, 60, batch_number="AMW-1",
                  cost_price=Decimal("10.00"))

    move = TransferRequest.all_objects.create(
        tenant=tenant, from_item=wholesale, to_item=retail,
        requested_quantity=25, requested_by=counter["staff"],
    )
    move.approve(20, user=counter["admin"])

    assert wholesale.quantity_on_hand == 40      # 60 - 20
    assert retail.quantity_on_hand == 120        # 100 + 20
    assert move.approved_quantity == 20
    assert move.status == TransferRequest.Status.APPROVED
    kinds = StockMovement.all_objects.filter(kind=StockMovement.Kind.TRANSFER)
    assert sorted(m.quantity for m in kinds) == [-20, 20]


def test_a_transfer_the_shelf_cannot_cover_moves_nothing(counter):
    tenant, retail = counter["tenant"], counter["item"]
    wholesale = StockItem.all_objects.create(
        tenant=tenant, name="Amoxicillin 250mg (pack)", sku="AMOX250W2",
        store=Store.WHOLESALE, cost_price=Decimal("10.00"),
    )
    receive_stock(wholesale, 5, batch_number="AMW-2")
    move = TransferRequest.all_objects.create(
        tenant=tenant, from_item=wholesale, to_item=retail, requested_quantity=50,
    )
    with pytest.raises(OutOfStock):
        move.approve(50)
    assert wholesale.quantity_on_hand == 5
    assert retail.quantity_on_hand == 100


# --- prescriber dues ------------------------------------------------------

def test_a_script_pays_its_prescriber_once_per_sale_and_once_per_script(counter):
    tenant = counter["tenant"]
    prescriber = Prescriber.all_objects.create(
        tenant=tenant, name="Dr Ada Eze", commission_rate=Decimal("10.00"),
        consult_fee_b=Decimal("2000.00"),
    )
    rx = Prescription.all_objects.create(
        tenant=tenant, prescriber=prescriber, customer_name="Chidi Okafor",
        consultation_category="B",
    )
    # The band's fee is snapshotted when the script is written up.
    assert rx.consultation_fee == Decimal("2000.00")

    sale = _sell(counter, quantity=4, rx=rx.pk)
    sale.refresh_from_db()

    commission = PrescriberCommission.all_objects.get(prescription=rx)
    payout = ConsultationPayout.all_objects.get(prescription=rx)
    assert commission.commission_amount == Decimal("10.00")   # 10% of 100.00
    assert payout.consultation_fee == Decimal("2000.00")

    # Filling more off the same script raises another commission, never a
    # second consultation fee — the patient was consulted once.
    rx.raise_prescriber_dues(sale)
    assert PrescriberCommission.all_objects.filter(prescription=rx).count() == 1
    assert ConsultationPayout.all_objects.filter(prescription=rx).count() == 1
    assert prescriber.outstanding["total"] == Decimal("2010.00")


# --- till and reports -----------------------------------------------------

def test_a_cash_expense_comes_out_of_the_drawer_it_was_paid_from(counter):
    tenant = counter["tenant"]
    till = TillSession.all_objects.create(
        tenant=tenant, opened_by=counter["staff"], opening_float=Decimal("5000.00"),
    )
    sale = _sell(counter, quantity=4)
    sale.record_payment(Decimal("100.00"), till=till, user=counter["staff"])

    category = ExpenseCategory.all_objects.create(tenant=tenant, name="Transport")
    Expense.all_objects.create(
        tenant=tenant, category=category, amount=Decimal("800.00"),
        payment_source=Expense.Source.CASH, till_session=till,
    )

    assert till.cash_in == Decimal("100.00")
    assert till.cash_out == Decimal("800.00")
    assert till.expected_amount == Decimal("4300.00")   # 5000 + 100 - 800


def test_a_refund_lands_on_the_day_it_happened_not_the_day_of_the_sale(counter):
    """The report must not reopen a closed month to net off a later refund."""
    sale = _sell(counter, quantity=10)
    sale.record_payment(sale.patient_payable, user=counter["staff"])
    line = SaleItem.all_objects.get(sale=sale)
    record_return(line, 4, refund_method=ReturnRecord.RefundMethod.CASH)

    today = str(timezone.localdate())
    yesterday = str(timezone.localdate() - timedelta(days=1))
    client = _client(counter["admin"], counter["tenant"])

    today_report = client.get(f"/api/reports/sales/?from={today}&to={today}").data
    assert today_report["total_revenue"] == Decimal("150.00")   # 250 sold - 100 back
    assert today_report["total_refunds"] == Decimal("100.00")

    # A window that ends before the sale sees neither the sale nor its refund.
    earlier = client.get(f"/api/reports/sales/?from={yesterday}&to={yesterday}").data
    assert earlier["total_revenue"] == Decimal("0.00")
    assert earlier["total_refunds"] == Decimal("0.00")


def test_profit_flags_lines_that_carry_no_cost(counter):
    """An uncosted line is left out of cost of goods, never treated as free."""
    tenant = counter["tenant"]
    free = StockItem.all_objects.create(
        tenant=tenant, name="Sample sachet", sku="SAMP1",
        cost_price=Decimal("0.00"), unit_price=Decimal("50.00"),
    )
    receive_stock(free, 10, batch_number="S-1", cost_price=Decimal("0.00"))
    _sell(counter, quantity=4)                       # costed: 4 x 10.00
    client = _client(counter["staff"], counter["tenant"])
    client.post("/api/pos/sales/",
                {"items": [{"item": free.pk, "quantity": 2}]}, format="json")

    report = _client(counter["admin"], counter["tenant"]).get(
        "/api/reports/profit/"
    ).data
    assert report["revenue"] == Decimal("200.00")    # 100 + 100
    assert report["cost"] == Decimal("40.00")        # only the costed line
    assert 0 < report["cost_coverage"] < 1


def test_hospital_list_counts_its_prescribers(counter):
    """The hospitals list carries how many doctors write from each one."""
    tenant = counter["tenant"]
    clinic = Hospital.all_objects.create(tenant=tenant, name="Ikeja General")
    Hospital.all_objects.create(tenant=tenant, name="Empty Clinic")
    for name in ("Dr Ada Eze", "Dr Musa Bello"):
        Prescriber.all_objects.create(tenant=tenant, name=name, hospital=clinic)

    rows = _client(counter["staff"], tenant).get(
        "/api/prescriptions/hospitals/"
    ).data["results"]
    counts = {r["name"]: r["prescriber_count"] for r in rows}
    assert counts == {"Ikeja General": 2, "Empty Clinic": 0}
