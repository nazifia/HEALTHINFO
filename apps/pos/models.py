"""Point of sale: dispensing, taking money, and the paperwork around it.

* ``Sale`` is one dispensing event. Its lines are allocated first-expiry-
  first-out across batches, so a sale of 30 tablets can draw from two
  consignments and still say which.
* ``SalePayment`` says how each part of the money actually arrived, and into
  whose drawer. ``TillSession`` is that drawer, float to close-of-day count.
* ``PaymentRequest`` is the dispenser's basket handed to a cashier, for
  counters where the person who picks the drugs is not the person who takes
  the money.
* ``ReturnRecord`` is a line coming back: stock returns to its batch and the
  refund goes out the way the pharmacy chose.
* ``PurchaseOrder`` is what was asked of a supplier and what has landed.
* ``Expense`` is money that left the till for something other than stock.
* ``Notification`` is what the app tells staff about: low stock, expiries, a
  waiting payment request.

ponytail: the moved tables keep their original ``pharmacy_*`` names
(``db_table`` below). The models changed app; the rows did not.
"""
from decimal import Decimal
from uuid import uuid4

from django.db import models, transaction
from django.utils import timezone

from apps.inventory.models import (
    OutOfStock,
    StockBatch,
    StockItem,
    StockMovement,
    receive_stock,
)
from apps.tenants.models import TenantOwnedModel

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value):
    """Round to kobo. Every stored amount goes through this."""
    return Decimal(value).quantize(MONEY)


class Cashier(TenantOwnedModel):
    """A user who is allowed to take money, and at which counter.

    Separate from the user's role because the two answer different questions:
    the role says what someone may do in the system, this says which till they
    sit at. A pharmacist covering the wholesale counter needs the second
    without changing the first.
    """

    class Kind(models.TextChoices):
        RETAIL = "retail"
        WHOLESALE = "wholesale"
        BOTH = "both"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="cashier"
    )
    code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.RETAIL)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "code")

    def __str__(self):
        return f"{self.name or self.user_id} ({self.code})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"CSH-{uuid4().hex[:8].upper()}"
        if not self.name and self.user_id:
            self.name = self.user.get_full_name() or self.user.get_username()
        super().save(*args, **kwargs)

    def serves(self, store):
        return self.kind == self.Kind.BOTH or self.kind == store


class TillSession(TenantOwnedModel):
    """One cashier's drawer, from the float it opens with to the count at close.

    Reconciliation is a single count against ``expected_amount``: the float,
    plus every note taken over the counter, less the change handed back. Which
    sales made up that total is answered by the sales pointing at the session.
    """

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="till_sessions"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="till_sessions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    opening_float = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Null until the drawer is counted - a closed drawer always has one.
    counted_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "pharmacy_tillsession"
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "opened_by"], condition=models.Q(status="open"),
                name="one_open_till_per_cashier",
            )
        ]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self):
        return f"Till {self.pk} ({self.status})"

    @property
    def _cash(self):
        """(notes in, change out) from this drawer's payment rows.

        ponytail: summed on read - a shift is a few hundred rows, so there are
        no running totals to drift out of step with the payments themselves.
        """
        # all_objects: the drawer is already this tenant's, so its own payments
        # are too - and the totals must not depend on who is asking.
        totals = SalePayment.all_objects.filter(till_session=self).aggregate(
            tendered=models.Sum("tendered"), change=models.Sum("change")
        )
        return _money(totals["tendered"] or 0), _money(totals["change"] or 0)

    @property
    def cash_in(self):
        """Notes taken over the counter into this drawer."""
        return self._cash[0]

    @property
    def change_out(self):
        """Change handed back out of this drawer."""
        return self._cash[1]

    @property
    def cash_out(self):
        """Cash expenses paid out of this drawer — money that left the till."""
        total = Expense.all_objects.filter(
            till_session=self, payment_source=Expense.Source.CASH
        ).aggregate(t=models.Sum("amount"))["t"]
        return _money(total or 0)

    @property
    def expected_amount(self):
        """What should be in the drawer: float, plus cash in, less change and
        any cash expense paid out of it."""
        tendered, change = self._cash
        return _money(self.opening_float + tendered - change - self.cash_out)

    @property
    def variance(self):
        """Counted less expected. None while open; negative means short."""
        if self.counted_amount is None:
            return None
        return _money(self.counted_amount - self.expected_amount)

    @classmethod
    def open_for(cls, user):
        """The cashier's open drawer, or None - a payment never waits on one."""
        return cls.objects.filter(opened_by=user, status=cls.Status.OPEN).first()

    def close(self, counted, *, notes=""):
        """Count the drawer and shut it.

        The variance is recorded, never corrected: a short drawer is a fact to
        explain, not a number to adjust until it agrees.
        """
        if self.status == self.Status.CLOSED:
            raise ValueError("This drawer is already closed.")
        counted = _money(counted)
        if counted < 0:
            raise ValueError("A counted drawer cannot be negative.")
        self.counted_amount = counted
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        if notes:
            self.notes = notes
        self.save(update_fields=["counted_amount", "status", "closed_at", "notes",
                                 "updated_at"])
        return self

    @property
    def totals(self):
        """What went through this drawer, by how the money arrived."""
        rows = SalePayment.all_objects.filter(till_session=self).values(
            "method"
        ).annotate(applied=models.Sum("applied"), n=models.Count("id"))
        by_method = {row["method"]: _money(row["applied"] or 0) for row in rows}
        return {
            "payments": sum(row["n"] for row in rows),
            "cash_in": self.cash_in,
            "change_out": self.change_out,
            "cash_out": self.cash_out,
            "by_method": by_method,
            "expected": self.expected_amount,
            "variance": self.variance,
        }


class Sale(TenantOwnedModel):
    """One dispensing event: what left the shelf, at what price, paid how.

    Money splits two ways and the two must always agree:
    ``total = patient_payable + hmo_payable``. A cash sale has an empty HMO
    side; an insured sale splits by the member's coverage. The patient side is
    what ``amount_paid`` settles; the HMO side is chased through a ``Claim``.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash"
        CARD = "card", "Card / POS"
        TRANSFER = "transfer"
        WALLET = "wallet"
        HMO = "hmo"  # insurer-covered; a co-payment may still be due
        SPLIT = "split"

    class Status(models.TextChoices):
        PENDING = "pending"    # dispensed, patient side not settled
        PAID = "paid"
        # Goods went out against a wallet that could not cover them. Real debt,
        # recorded on the customer, and deliberately kept out of revenue until
        # it is paid.
        CREDIT = "credit"
        PARTIAL_RETURN = "partial_return"
        RETURNED = "returned"
        CANCELLED = "cancelled"

    # Statuses that count as money earned. A cancelled sale never happened; a
    # credit sale has not been paid for; a fully returned one was undone.
    REVENUE_STATUSES = (Status.PENDING, Status.PAID, Status.PARTIAL_RETURN)

    reference = models.CharField(max_length=30)
    # Walk-in sales have no patient. An insured sale always does - the claim
    # needs someone to name (enforced by the serializer).
    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    customer = models.ForeignKey(
        "customers.Customer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales",
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales",
    )
    prescription = models.ForeignKey(
        "analytics.Prescription", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    # The dispensing prescription this sale filled, when it came from one.
    rx = models.ForeignKey(
        "prescriptions.Prescription", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sales",
    )
    enrollment = models.ForeignKey(
        "pharmacy.HmoEnrollment", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales",
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    is_wholesale = models.BooleanField(default=False)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # A prescriber's consultation fee, folded into the total and owed on to
    # them. Never itemised on the customer's receipt — see
    # ``prescriptions.ConsultationPayout``.
    consultation_fee = models.DecimalField(max_digits=12, decimal_places=2,
                                           default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    patient_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hmo_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Cash handed over the counter, which can exceed what is owed. The excess is
    # change given back, never money banked on the sale.
    amount_tendered = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    served_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    cashier = models.ForeignKey(
        Cashier, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales",
    )
    buyer_name = models.CharField(max_length=200, blank=True)
    buyer_address = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "pharmacy_sale"
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "payment_method"]),
            models.Index(fields=["tenant", "is_wholesale"]),
        ]

    def __str__(self):
        return f"{self.reference} ({self.total})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SL{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def buyer(self):
        """Who this sale was for, as a name to print."""
        if self.customer_id:
            return self.customer.name
        if self.patient_id:
            return self.patient.full_name
        return self.buyer_name or "Walk-in"

    @property
    def balance_due(self):
        """What the patient still owes. Never negative - an overpayment is
        change given, not a debt owed back through this field."""
        return max(_money(self.patient_payable - self.amount_paid), ZERO)

    @property
    def change_due(self):
        """Change handed back: whatever was tendered beyond the patient's side."""
        return max(_money(self.amount_tendered - self.amount_paid), ZERO)

    @property
    def coverage_percent(self):
        """Insurer's share of this sale, 0 when it isn't an insured sale."""
        if self.payment_method != self.PaymentMethod.HMO or not self.enrollment_id:
            return ZERO
        return Decimal(self.enrollment.effective_coverage)

    @property
    def cost_of_goods(self):
        """What the dispensed units cost to buy, returns netted off."""
        total = ZERO
        for line in SaleItem.all_objects.filter(sale=self):
            total += line.cost_price * (line.quantity - line.return_quantity)
        return _money(total)

    @property
    def gross_profit(self):
        return _money(self.total - self.cost_of_goods)

    # --- dispensing ------------------------------------------------------
    def add_line(self, item, quantity, *, unit_price=None, discount=ZERO,
                 user=None):
        """Dispense ``quantity`` of ``item``, first-expiry-first-out.

        One line per batch drawn from, so a quantity that spans two
        consignments records which batch each unit came from - that is what a
        recall or a query about an expiry date needs. Stock is decremented and
        a DISPENSE movement written for each. Raises ``OutOfStock`` (nothing
        committed) when sellable stock can't cover the request.
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        price = _money(unit_price if unit_price is not None else item.unit_price)
        lines = []
        with transaction.atomic():
            remaining = quantity
            batches = list(item.sellable_batches().select_for_update())
            available = sum(b.quantity for b in batches)
            if available < quantity:
                raise OutOfStock(item, quantity, available)
            for batch in batches:
                if remaining <= 0:
                    break
                take = min(batch.quantity, remaining)
                batch.quantity -= take
                batch.save(update_fields=["quantity", "updated_at"])
                lines.append(SaleItem.all_objects.create(
                    tenant=self.tenant, sale=self, item=item, batch=batch,
                    name=item.name, brand=item.brand, form=item.form,
                    unit=item.unit, barcode=item.barcode,
                    quantity=take, unit_price=price,
                    # The line discount is charged once, against the first batch
                    # drawn, not repeated per batch.
                    discount=_money(discount) if not lines else ZERO,
                    cost_price=batch.cost_price,
                ))
                StockMovement.all_objects.create(
                    tenant=self.tenant, item=item, batch=batch, sale=self,
                    kind=StockMovement.Kind.DISPENSE, quantity=-take, user=user,
                    reason=f"Sale {self.reference}",
                )
                remaining -= take
            DispensingLog.all_objects.create(
                tenant=self.tenant, sale=self, item=item, user=user,
                name=item.name, brand=item.brand, form=item.form, unit=item.unit,
                quantity=quantity, amount=_money(price * quantity),
                discount=_money(discount),
            )
            self.recalculate()
        return lines

    def recalculate(self):
        """Re-derive every money field from the lines. Cheap, so call it freely.

        The patient/HMO split is computed here rather than stored per line: the
        insurer covers a percentage of the bill, not of individual drugs.
        """
        subtotal = ZERO
        discount = ZERO
        for line in SaleItem.all_objects.filter(sale=self):
            subtotal += line.gross
            discount += line.discount
        # The consultation fee rides on the bill without appearing on it, so it
        # is added after the discount rather than being discountable.
        total = _money(
            max(subtotal - discount, ZERO) + Decimal(self.consultation_fee)
        )
        hmo_share = _money(total * self.coverage_percent / Decimal("100"))
        self.subtotal = _money(subtotal)
        self.discount = _money(discount)
        self.total = total
        self.hmo_payable = hmo_share
        # Patient side is the remainder, so rounding can never lose or invent a
        # kobo: the two sides always add back to the total.
        self.patient_payable = _money(total - hmo_share)
        self.save(update_fields=["subtotal", "discount", "total", "hmo_payable",
                                 "patient_payable", "updated_at"])
        return self

    def default_payment_method(self):
        """How money arrives by default: an insured sale's co-payment is cash."""
        if self.payment_method == self.PaymentMethod.HMO:
            return SalePayment.Method.CASH
        if self.payment_method == self.PaymentMethod.SPLIT:
            return SalePayment.Method.CASH
        return self.payment_method

    def record_payment(self, amount, *, method=None, till=None, user=None):
        """Take cash tendered; mark PAID once the patient's side is covered.

        ``amount`` is what was handed over, which at a counter is often more
        than the bill. Only what is owed lands on ``amount_paid``; the rest is
        change (see ``change_due``) rather than a credit sitting on the sale.

        ``method`` is how this payment arrived - the sale's own method unless
        the counter says otherwise, which is how a card sale can still be part
        settled in cash. Only cash reaches ``till``, the cashier's open drawer.
        """
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("Payment must be positive.")
        if self.status in (self.Status.CANCELLED, self.Status.RETURNED):
            raise ValueError("A cancelled or returned sale cannot take payment.")
        if self.balance_due <= 0:
            raise ValueError("This sale is settled; there is nothing left to pay.")
        method = method or self.default_payment_method()
        if method not in SalePayment.Method.values:
            raise ValueError(f"{method} is not a way to take money over the counter.")
        change = max(_money(amount - self.balance_due), ZERO)
        applied = min(amount, self.balance_due)
        with transaction.atomic():
            SalePayment.all_objects.create(
                tenant=self.tenant, sale=self, method=method, tendered=amount,
                applied=applied, change=change, taken_by=user,
                till_session=till if method == SalePayment.Method.CASH else None,
            )
            self.amount_tendered = _money(self.amount_tendered + amount)
            self.amount_paid = _money(self.amount_paid + applied)
            if self.amount_paid >= self.patient_payable:
                self.status = self.Status.PAID
            self.save(update_fields=["amount_tendered", "amount_paid", "status",
                                     "updated_at"])
        return self

    def pay_from_wallet(self, *, user=None):
        """Settle the patient's side out of the customer's wallet.

        A wallet that cannot cover the bill pays what it holds and the rest
        becomes the customer's debt: the goods have already left the shelf.
        The sale is then CREDIT, which keeps it out of revenue until the debt
        is paid off.
        """
        if not self.customer_id:
            raise ValueError("A wallet payment needs a customer.")
        due = self.balance_due
        if due <= 0:
            raise ValueError("This sale is settled; there is nothing left to pay.")
        with transaction.atomic():
            paid, credit, _row = self.customer.charge(
                due, note=f"Sale {self.reference}"
            )
            if paid > 0:
                SalePayment.all_objects.create(
                    tenant=self.tenant, sale=self, method=SalePayment.Method.WALLET,
                    tendered=paid, applied=paid, change=ZERO, taken_by=user,
                )
                self.amount_tendered = _money(self.amount_tendered + paid)
                self.amount_paid = _money(self.amount_paid + paid)
            self.status = self.Status.CREDIT if credit > 0 else self.Status.PAID
            self.save(update_fields=["amount_tendered", "amount_paid", "status",
                                     "updated_at"])
        return self, credit

    def cancel(self, *, reason="", user=None):
        """Reverse the sale: every dispensed unit goes back to its own batch.

        Stock returns to the batch it came from (not to any batch), each with a
        RETURN movement, and an open claim is cancelled with it. The sale rows
        stay - a cancelled sale is history, not a hole in the numbering.
        """
        from apps.pharmacy.models import Claim

        if self.status == self.Status.CANCELLED:
            return self
        with transaction.atomic():
            for line in SaleItem.all_objects.filter(sale=self).select_related("batch"):
                if line.batch_id:
                    batch = StockBatch.all_objects.select_for_update().get(
                        pk=line.batch_id
                    )
                    batch.quantity += line.quantity
                    batch.save(update_fields=["quantity", "updated_at"])
                StockMovement.all_objects.create(
                    tenant=self.tenant, item_id=line.item_id, batch_id=line.batch_id,
                    sale=self, kind=StockMovement.Kind.RETURN,
                    quantity=line.quantity, user=user,
                    reason=reason or f"Sale {self.reference} cancelled",
                )
            claim = Claim.all_objects.filter(sale=self).first()
            if claim and claim.status not in (Claim.Status.PAID,
                                              Claim.Status.CANCELLED):
                claim.status = Claim.Status.CANCELLED
                claim.save(update_fields=["status", "updated_at"])
            DispensingLog.all_objects.filter(sale=self).update(
                status=DispensingLog.Status.RETURNED
            )
            self.status = self.Status.CANCELLED
            self.save(update_fields=["status", "updated_at"])
        return self

    def sync_return_status(self):
        """Follow what has come back: partly returned, or returned outright."""
        if self.status == self.Status.CANCELLED:
            return self
        lines = list(SaleItem.all_objects.filter(sale=self))
        returned = sum(line.return_quantity for line in lines)
        if returned <= 0:
            return self
        status = (self.Status.RETURNED
                  if returned >= sum(line.quantity for line in lines)
                  else self.Status.PARTIAL_RETURN)
        if status != self.status:
            self.status = status
            self.save(update_fields=["status", "updated_at"])
        return self


class SaleItem(TenantOwnedModel):
    """One batch's worth of one item on a sale.

    The item's descriptive fields are copied at dispensing time so a receipt
    reprinted after the price list moved on — or after the item row was
    deleted — still says what was actually handed over. ``cost_price`` is
    copied for the same reason, so margin reporting stays true.
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="sale_lines"
    )
    batch = models.ForeignKey(
        StockBatch, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sale_lines",
    )
    name = models.CharField(max_length=255, blank=True)
    brand = models.CharField(max_length=200, blank=True)
    form = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    return_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "pharmacy_saleitem"
        ordering = ("id",)
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return f"{self.quantity} x {self.item_id} @ {self.unit_price}"

    @property
    def gross(self):
        return _money(self.unit_price * self.quantity)

    @property
    def line_total(self):
        return _money(max(self.gross - self.discount, ZERO))

    @property
    def margin(self):
        return _money(self.line_total - self.cost_price * self.quantity)

    @property
    def returnable(self):
        return max(self.quantity - self.return_quantity, 0)


class SalePayment(TenantOwnedModel):
    """One payment taken against a sale: how much, in what form, into which drawer.

    The sale keeps the running totals; these rows say how the money actually
    arrived, so a cash co-payment on an insured sale still reaches the drawer
    while the card half of the same bill does not.
    """

    class Method(models.TextChoices):
        CASH = "cash"
        CARD = "card", "Card / POS"
        TRANSFER = "transfer"
        WALLET = "wallet"

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    # PROTECT: a counted drawer cannot lose the payments it was counted against.
    till_session = models.ForeignKey(
        TillSession, null=True, blank=True, on_delete=models.PROTECT,
        related_name="payments",
    )
    method = models.CharField(
        max_length=20, choices=Method.choices, default=Method.CASH
    )
    tendered = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # What settled the bill; the rest went back as change.
    applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taken_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_payments",
    )

    class Meta:
        db_table = "pharmacy_salepayment"
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=["tenant", "till_session"])]

    def __str__(self):
        return f"{self.tendered} {self.method} on sale {self.sale_id}"


class DispensingLog(TenantOwnedModel):
    """Every item handed over, across every sale.

    The sale answers "what did this cost"; this answers "who gave out what,
    and when" — the question a controlled-drug register or a query about a
    single dispensing event asks, without reading through sales.
    """

    class Status(models.TextChoices):
        DISPENSED = "dispensed"
        PARTIALLY_RETURNED = "partially_returned"
        RETURNED = "returned"

    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.CASCADE,
        related_name="dispensing_logs",
    )
    item = models.ForeignKey(
        StockItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dispensing_logs",
    )
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dispensing_logs",
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=200, blank=True)
    form = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DISPENSED
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "item"]),
        ]

    def __str__(self):
        return f"{self.name} x{self.quantity} ({self.status})"


class PaymentRequest(TenantOwnedModel):
    """A dispenser's basket, sent to a cashier to be paid for.

    Where one person picks the drugs and another takes the money, this is the
    handover. It is not a sale: nothing leaves the shelf until the cashier
    completes it, which is what turns it into one.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    reference = models.CharField(max_length=30)
    dispenser = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="payment_requests"
    )
    cashier = models.ForeignKey(
        Cashier, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_requests",
    )
    customer = models.ForeignKey(
        "customers.Customer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_requests",
    )
    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_requests",
    )
    store = models.CharField(max_length=20, default="retail")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    buyer_name = models.CharField(max_length=200, blank=True)
    buyer_address = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_requests",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"{self.reference} ({self.status}: {self.total_amount})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PRQ{uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def _lines(self):
        return PaymentRequestItem.all_objects.filter(request=self)

    def recalculate(self):
        total = sum((line.subtotal for line in self._lines()), ZERO)
        self.total_amount = _money(total)
        self.save(update_fields=["total_amount", "updated_at"])
        return self

    def accept(self, cashier):
        """A cashier takes the request. Nothing has moved yet."""
        if self.status != self.Status.PENDING:
            raise ValueError("Only a pending request can be accepted.")
        self.cashier = cashier
        self.status = self.Status.ACCEPTED
        self.save(update_fields=["cashier", "status", "updated_at"])
        return self

    def reject(self, reason=""):
        if self.status not in (self.Status.PENDING, self.Status.ACCEPTED):
            raise ValueError("Only an open request can be rejected.")
        self.status = self.Status.REJECTED
        if reason:
            self.notes = reason
        self.save(update_fields=["status", "notes", "updated_at"])
        return self

    def cancel(self):
        """The dispenser withdraws the basket before it is paid for."""
        if self.status == self.Status.COMPLETED:
            raise ValueError("A completed request cannot be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])
        return self

    def complete(self, *, user=None, payment_method=Sale.PaymentMethod.CASH):
        """Turn the basket into a sale. This is where stock actually moves.

        All or nothing: a line that cannot be filled leaves the request open
        rather than half-dispensing a basket someone is standing at the
        counter waiting for.
        """
        if self.status not in (self.Status.PENDING, self.Status.ACCEPTED):
            raise ValueError("Only an open request can be completed.")
        lines = list(self._lines().select_related("item"))
        if not lines:
            raise ValueError("The request has nothing on it.")
        with transaction.atomic():
            sale = Sale.all_objects.create(
                tenant=self.tenant, customer=self.customer, patient=self.patient,
                payment_method=payment_method, served_by=self.dispenser,
                cashier=self.cashier, buyer_name=self.buyer_name,
                buyer_address=self.buyer_address, notes=self.notes,
                is_wholesale=self.store == "wholesale",
            )
            for line in lines:
                if line.item_id is None:
                    raise ValueError(f"{line.name} is not on the item list.")
                sale.add_line(line.item, line.quantity,
                              unit_price=line.unit_price, discount=line.discount,
                              user=user)
            self.sale = sale
            self.status = self.Status.COMPLETED
            self.save(update_fields=["sale", "status", "updated_at"])
        return sale


class PaymentRequestItem(TenantOwnedModel):
    """One line on a basket waiting to be paid for."""

    request = models.ForeignKey(
        PaymentRequest, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        StockItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_request_lines",
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=200, blank=True)
    form = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return f"{self.name} x{self.quantity}"

    @property
    def subtotal(self):
        return _money(max(self.unit_price * self.quantity - self.discount, ZERO))

    def save(self, *args, **kwargs):
        if self.item_id and not self.name:
            self.name = self.item.name
            self.brand = self.item.brand
            self.form = self.item.form
            self.unit = self.item.unit
            if not self.unit_price:
                self.unit_price = self.item.unit_price
        super().save(*args, **kwargs)


class ReturnRecord(TenantOwnedModel):
    """A line coming back: stock to its batch, money back to the customer.

    Refunds are recorded on the day they happen, never against the day of the
    original sale — a refund does not rewrite the month its sale fell in.
    """

    class RefundMethod(models.TextChoices):
        WALLET = "wallet"
        CASH = "cash"
        ORIGINAL = "original", "Original method"

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="returns")
    line = models.ForeignKey(
        SaleItem, on_delete=models.CASCADE, related_name="returns"
    )
    quantity = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_method = models.CharField(
        max_length=20, choices=RefundMethod.choices, default=RefundMethod.WALLET
    )
    reason = models.CharField(max_length=300, blank=True)
    returned_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_returns",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "refund_method"]),
        ]

    def __str__(self):
        return f"Return {self.quantity} from {self.sale_id}"


def record_return(line, quantity, *, refund_method=ReturnRecord.RefundMethod.WALLET,
                  reason="", user=None):
    """Take units back onto the shelf and refund what they were charged at.

    The refund is the line's own price less its share of the line discount, so
    a discounted sale is not refunded at full price. A wallet refund lands on
    the customer's balance; cash goes out of the drawer and is netted off the
    day's takings by the sales report.
    """
    quantity = int(quantity)
    if quantity <= 0:
        raise ValueError("A return must be at least one unit.")
    if quantity > line.returnable:
        raise ValueError(f"Only {line.returnable} unit(s) can still be returned.")
    sale = line.sale
    if sale.status == Sale.Status.CANCELLED:
        raise ValueError("A cancelled sale has already been reversed in full.")
    unit_refund = _money(line.line_total / line.quantity) if line.quantity else ZERO
    amount = _money(unit_refund * quantity)
    with transaction.atomic():
        if line.batch_id:
            batch = StockBatch.all_objects.select_for_update().get(pk=line.batch_id)
            batch.quantity += quantity
            batch.save(update_fields=["quantity", "updated_at"])
        StockMovement.all_objects.create(
            tenant=sale.tenant, item_id=line.item_id, batch_id=line.batch_id,
            sale=sale, kind=StockMovement.Kind.RETURN, quantity=quantity,
            user=user, reason=reason or f"Return on {sale.reference}",
        )
        line.return_quantity += quantity
        line.save(update_fields=["return_quantity", "updated_at"])
        record = ReturnRecord.all_objects.create(
            tenant=sale.tenant, sale=sale, line=line, quantity=quantity,
            amount=amount, refund_method=refund_method, reason=reason,
            returned_by=user,
        )
        if refund_method == ReturnRecord.RefundMethod.WALLET and sale.customer_id:
            sale.customer.refund(amount, note=f"Return on {sale.reference}")
        DispensingLog.all_objects.filter(sale=sale, item_id=line.item_id).update(
            status=(DispensingLog.Status.RETURNED if line.returnable == 0
                    else DispensingLog.Status.PARTIALLY_RETURNED)
        )
        sale.sync_return_status()
    return record


class ExpenseCategory(TenantOwnedModel):
    """What money that isn't stock gets spent on: rent, power, transport."""

    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "expense categories"
        ordering = ("name", "id")
        unique_together = ("tenant", "name")

    def __str__(self):
        return self.name


class Expense(TenantOwnedModel):
    """Money out that bought no stock.

    ``payment_source`` says whether it left the cash drawer or came out of a
    bank balance, because a cash expense changes what the till should count at
    close and a transfer does not.
    """

    class Source(models.TextChoices):
        CASH = "cash"
        OTHER = "other", "Bank / card / transfer"

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses",
    )
    till_session = models.ForeignKey(
        TillSession, null=True, blank=True, on_delete=models.PROTECT,
        related_name="expenses",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=300, blank=True)
    payment_source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.CASH
    )
    date = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_expenses",
    )

    class Meta:
        ordering = ("-date", "-id")
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["tenant", "payment_source"]),
        ]

    def __str__(self):
        return f"{self.description or self.category_id} — {self.amount} ({self.date})"


class Notification(TenantOwnedModel):
    """What the app tells one member of staff about, and how loudly."""

    class Kind(models.TextChoices):
        LOW_STOCK = "low_stock", "Low stock"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        EXPIRY = "expiry", "Expiry alert"
        PAYMENT_REQUEST = "payment_request", "Payment request"
        SYSTEM = "system", "System message"

    class Priority(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="pharmacy_notifications"
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    item = models.ForeignKey(
        StockItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "user", "is_read"])]

    def __str__(self):
        return f"[{self.priority}] {self.title}"


class PurchaseOrder(TenantOwnedModel):
    """What the pharmacy asked a supplier for, and how much of it has arrived.

    Deliveries rarely match the order: a supplier part-ships, back-orders the
    rest, and invoices at a different price. So the order holds what was
    ordered and each line counts what has actually been received; the status
    follows from that count rather than being set by hand.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"          # being written, not yet sent
        SUBMITTED = "submitted"  # sent to the supplier, nothing received
        PARTIAL = "partial"      # some lines short
        RECEIVED = "received"    # everything ordered has arrived
        CANCELLED = "cancelled"

    reference = models.CharField(max_length=30)
    supplier = models.ForeignKey(
        "inventory.Supplier", on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    expected_date = models.DateField(null=True, blank=True)
    ordered_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="purchase_orders",
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "pharmacy_purchaseorder"
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["tenant", "supplier"]),
        ]

    def __str__(self):
        return f"{self.reference} ({self.supplier_id})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PO{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def _lines(self):
        return PurchaseOrderLine.all_objects.filter(order=self)

    @property
    def total_cost(self):
        """What the order is worth at the prices it was placed at."""
        total = self._lines().aggregate(
            v=models.Sum(models.F("quantity_ordered") * models.F("unit_cost"),
                         output_field=models.DecimalField(max_digits=14,
                                                          decimal_places=2))
        )["v"]
        return _money(total or 0)

    @property
    def is_fully_received(self):
        lines = list(self._lines())
        return bool(lines) and all(line.outstanding == 0 for line in lines)

    def submit(self):
        """Send the order. Only a draft is sent, and only with something on it."""
        if self.status != self.Status.DRAFT:
            raise ValueError("Only a draft order can be submitted.")
        if not self._lines().exists():
            raise ValueError("An order needs at least one line.")
        self.status = self.Status.SUBMITTED
        self.save(update_fields=["status", "updated_at"])
        return self

    def cancel(self):
        """Cancel what has not arrived. Stock already received stays received."""
        if self.status == self.Status.RECEIVED:
            raise ValueError("A fully received order cannot be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])
        return self

    def sync_status(self):
        """Move the status to match what has been received. Called after a receipt."""
        if self.status == self.Status.CANCELLED:
            return self
        received = any(line.quantity_received for line in self._lines())
        if self.is_fully_received:
            status = self.Status.RECEIVED
        elif received:
            status = self.Status.PARTIAL
        else:
            status = (self.Status.SUBMITTED if self.status != self.Status.DRAFT
                      else self.Status.DRAFT)
        if status != self.status:
            self.status = status
            self.save(update_fields=["status", "updated_at"])
        return self


class PurchaseOrderLine(TenantOwnedModel):
    """One item on an order: how many were asked for, how many have landed."""

    order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="purchase_lines"
    )
    quantity_ordered = models.PositiveIntegerField(default=1)
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "pharmacy_purchaseorderline"
        ordering = ("id",)
        unique_together = ("order", "item")
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return f"{self.quantity_received}/{self.quantity_ordered} of {self.item_id}"

    @property
    def outstanding(self):
        return max(self.quantity_ordered - self.quantity_received, 0)


def receive_purchase_line(line, quantity, *, batch_number, expiry_date=None,
                          unit_cost=None, user=None):
    """Book a delivery against an order line: real stock in, line counted up.

    Over-receiving is refused. A supplier who ships more than was ordered has
    changed the order, and that is a decision someone makes on the order —
    not a silent extra on the shelf.
    """
    if quantity <= 0:
        raise ValueError("Received quantity must be positive.")
    if quantity > line.outstanding:
        raise ValueError(
            f"Only {line.outstanding} unit(s) outstanding on this line."
        )
    order = line.order
    if order.status == PurchaseOrder.Status.CANCELLED:
        raise ValueError("A cancelled order cannot receive stock.")
    cost = unit_cost if unit_cost is not None else line.unit_cost
    with transaction.atomic():
        batch = receive_stock(
            line.item, quantity, batch_number=batch_number,
            expiry_date=expiry_date or line.expiry_date, cost_price=cost,
            supplier=order.supplier, user=user,
        )
        line.quantity_received += quantity
        if unit_cost is not None:
            # The invoice price is what the stock actually cost; keep it.
            line.unit_cost = _money(unit_cost)
        line.save(update_fields=["quantity_received", "unit_cost", "updated_at"])
        order.sync_status()
    return batch
