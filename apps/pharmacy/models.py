"""Pharmacy: stock, sales and HMO claims for one facility (tenant).

Three ledgers, each answering a different question:

* **Stock** - ``StockItem`` is what the pharmacy sells, ``StockBatch`` is a
  physical consignment of it (its own expiry and cost price), and
  ``StockMovement`` is the append-only trail of every unit in or out. Batch
  quantity is the fast read; the movement rows are the audit that explains it.
* **Sales** - a ``Sale`` is one dispensing event. Its lines are allocated
  first-expiry-first-out across batches, so a sale of 30 tablets can draw from
  two consignments and still say which.
* **Claims** - the HMO's share of a sale, followed from submission to payment.

Everything is tenant-owned: one pharmacy never sees another's stock, prices or
claims. ``apps.analytics.StockReport`` stays what it was - a de-identified
snapshot for central surveillance; this app is the operational record it
summarizes.
"""
from decimal import Decimal
from uuid import uuid4

from django.db import models, transaction
from django.utils import timezone

from apps.tenants.models import TenantOwnedModel

MONEY = Decimal("0.01")


def _money(value):
    """Round to kobo. Every stored amount goes through this."""
    return Decimal(value).quantize(MONEY)


class Supplier(TenantOwnedModel):
    """A distributor or manufacturer the pharmacy buys from.

    Batches point here rather than carrying a typed-in name, so "Emzor",
    "emzor" and "Emzor Pharma" stop being three suppliers when someone asks
    who supplied a recalled batch.
    """

    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "name")
        indexes = [models.Index(fields=["tenant", "is_active"])]

    def __str__(self):
        return self.name


class StockItem(TenantOwnedModel):
    """Something the pharmacy holds and sells - a drug or a consumable.

    ``medication`` links to the shared catalog when there is a match, so stock
    and prescriptions talk about the same drug; it stays optional because
    gloves and syringes are inventory too and are in no drug catalog.
    """

    class Form(models.TextChoices):
        TABLET = "tablet"
        CAPSULE = "capsule"
        SYRUP = "syrup"
        INJECTION = "injection"
        CREAM = "cream"
        DROPS = "drops"
        CONSUMABLE = "consumable"
        OTHER = "other"

    medication = models.ForeignKey(
        "catalog.Medication", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_items",
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, blank=True)
    form = models.CharField(max_length=20, choices=Form.choices, default=Form.TABLET)
    # What one sold unit is ("tablet", "bottle of 100ml"). Prices are per unit.
    unit = models.CharField(max_length=50, default="unit")
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Stock at or below this is "low" - the reorder signal the admin dashboard
    # and the low-stock endpoint read.
    reorder_level = models.PositiveIntegerField(default=0)
    prescription_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            # An SKU is unique per pharmacy when there is one; items with no SKU
            # are left alone (blank is not a duplicate of blank).
            models.UniqueConstraint(
                fields=["tenant", "sku"], condition=~models.Q(sku=""),
                name="pharmacy_stockitem_unique_sku_per_tenant",
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def _batches(self):
        """This item's batches, reached without the tenant thread-local.

        A batch belongs to the same tenant as its item, so scoping by the item
        the caller already holds is the same scope — and it keeps stock figures
        correct in a Celery task or a management command, where no tenant is
        bound and the scoped manager would answer zero.
        """
        return StockBatch.all_objects.filter(item=self)

    @property
    def quantity_on_hand(self):
        """Units across every batch, expired ones included.

        ponytail: one aggregate per item. List endpoints annotate instead, so
        this never runs in a loop; keep it that way if you add more listings.
        """
        return self._batches().aggregate(n=models.Sum("quantity"))["n"] or 0

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level

    def sellable_batches(self):
        """Batches that may be dispensed, first-expiry-first-out.

        Expired batches are excluded outright - they are still on the shelf and
        still count as stock on hand, but they may not be sold. Batches with no
        expiry sort last so dated stock always moves first.
        """
        return (
            self._batches().filter(quantity__gt=0)
            .exclude(expiry_date__lt=timezone.localdate())
            .order_by(models.F("expiry_date").asc(nulls_last=True), "id")
        )


class StockBatch(TenantOwnedModel):
    """One consignment of an item: its own expiry, cost and remaining quantity.

    ``quantity`` is the live figure sales decrement; ``quantity_received`` is
    what arrived and never changes, so shrinkage is the difference between them
    minus what the movement ledger accounts for.
    """

    item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="batches"
    )
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    quantity_received = models.PositiveIntegerField(default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # PROTECT: a supplier with stock history is not deleted out from under it.
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.PROTECT,
        related_name="batches",
    )
    received_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("expiry_date", "id")
        unique_together = ("tenant", "item", "batch_number")
        indexes = [
            models.Index(fields=["tenant", "item"]),
            models.Index(fields=["tenant", "expiry_date"]),
        ]

    def __str__(self):
        return f"{self.item_id}/{self.batch_number} ({self.quantity})"

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    def save(self, *args, **kwargs):
        if self._state.adding:
            # A new consignment arrives whole: received defaults to on hand.
            if not self.quantity_received:
                self.quantity_received = self.quantity
            if self.received_at is None:
                self.received_at = timezone.localdate()
        super().save(*args, **kwargs)


class StockMovement(TenantOwnedModel):
    """Append-only: every unit that entered or left, and why.

    ``quantity`` is signed - positive in, negative out - so the ledger sums to
    what should be on the shelf. Rows are never edited; a mistake is corrected
    by another movement.
    """

    class Kind(models.TextChoices):
        RECEIPT = "receipt"        # consignment received
        DISPENSE = "dispense"      # sold / given to a patient
        RETURN = "return"          # came back (cancelled sale, patient return)
        ADJUSTMENT = "adjustment"  # stock count correction
        WRITE_OFF = "write_off"    # expired, damaged, lost

    item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name="movements"
    )
    # SET_NULL: deleting a batch record must not erase the trail of what it moved.
    batch = models.ForeignKey(
        StockBatch, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movements",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    quantity = models.IntegerField()  # signed: + in, - out
    sale = models.ForeignKey(
        "pharmacy.Sale", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movements",
    )
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "item", "kind"]),
        ]

    def __str__(self):
        return f"{self.kind} {self.quantity} of item {self.item_id}"


class OutOfStock(Exception):
    """Not enough sellable stock to fill a line. Carries the shortfall."""

    def __init__(self, item, requested, available):
        self.item, self.requested, self.available = item, requested, available
        super().__init__(
            f"{item.name}: only {available} unit(s) available, {requested} requested."
        )


def receive_stock(item, quantity, *, batch_number, expiry_date=None,
                  cost_price=None, supplier=None, user=None):
    """Book a consignment in: batch topped up (or created) plus a RECEIPT row.

    Re-receiving the same batch number adds to that batch rather than creating
    a second one - the same physical batch arriving twice is one batch.
    """
    if quantity <= 0:
        raise ValueError("Received quantity must be positive.")
    with transaction.atomic():
        batch, created = StockBatch.all_objects.select_for_update().get_or_create(
            tenant=item.tenant, item=item, batch_number=batch_number,
            defaults={
                "expiry_date": expiry_date,
                "quantity": quantity,
                "quantity_received": quantity,
                "cost_price": _money(cost_price if cost_price is not None
                                     else item.cost_price),
                "supplier": supplier,
            },
        )
        if not created:
            batch.quantity += quantity
            batch.quantity_received += quantity
            if expiry_date:
                batch.expiry_date = expiry_date
            if cost_price is not None:
                batch.cost_price = _money(cost_price)
            if supplier:
                batch.supplier = supplier
            batch.save(update_fields=["quantity", "quantity_received",
                                      "expiry_date", "cost_price", "supplier",
                                      "updated_at"])
        StockMovement.all_objects.create(
            tenant=item.tenant, item=item, batch=batch,
            kind=StockMovement.Kind.RECEIPT, quantity=quantity, user=user,
            reason=f"Received from {supplier.name}" if supplier else "Stock received",
        )
    return batch


def adjust_stock(batch, new_quantity, *, reason, user=None,
                 kind=StockMovement.Kind.ADJUSTMENT):
    """Set a batch to a counted quantity and log the difference.

    This is the only sanctioned way to move stock outside a sale: a stock count
    correction or a write-off. The movement records the delta, so the ledger
    still explains the shelf.
    """
    if new_quantity < 0:
        raise ValueError("Quantity cannot be negative.")
    with transaction.atomic():
        locked = StockBatch.all_objects.select_for_update().get(pk=batch.pk)
        delta = new_quantity - locked.quantity
        locked.quantity = new_quantity
        locked.save(update_fields=["quantity", "updated_at"])
        if delta:
            StockMovement.all_objects.create(
                tenant=locked.tenant, item_id=locked.item_id, batch=locked,
                kind=kind, quantity=delta, user=user, reason=reason,
            )
    return locked


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
        Supplier, on_delete=models.PROTECT, related_name="purchase_orders"
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

    class Meta:
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
            expiry_date=expiry_date, cost_price=cost, supplier=order.supplier,
            user=user,
        )
        line.quantity_received += quantity
        if unit_cost is not None:
            # The invoice price is what the stock actually cost; keep it.
            line.unit_cost = _money(unit_cost)
        line.save(update_fields=["quantity_received", "unit_cost", "updated_at"])
        order.sync_status()
    return batch


class HMO(TenantOwnedModel):
    """An insurer the pharmacy bills - an HMO, or NHIA itself.

    ``coverage_percent`` is the scheme default: what the insurer pays of a
    covered sale, the rest being the patient's co-payment. NHIA's 90/10 drug
    split is just a row here with coverage 90, so the national scheme needs no
    special case in the sale logic.
    """

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    contact = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    coverage_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00")
    )
    # Some insurers want each claim as the sale happens; others only read the
    # monthly schedule. Off by default, so a claim waits for its ``ClaimBatch``.
    auto_submit_claims = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "name")
        verbose_name = "HMO"

    def __str__(self):
        return self.name


class HmoEnrollment(TenantOwnedModel):
    """A patient's membership of one scheme - the card they present.

    ``coverage_percent`` overrides the HMO's default when this member's plan
    differs; left blank, the scheme default applies.
    """

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="hmo_enrollments"
    )
    hmo = models.ForeignKey(HMO, on_delete=models.PROTECT, related_name="enrollments")
    member_number = models.CharField(max_length=100)
    plan = models.CharField(max_length=100, blank=True)
    coverage_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "hmo", "member_number")
        indexes = [models.Index(fields=["tenant", "patient"])]

    def __str__(self):
        return f"{self.member_number} ({self.hmo_id})"

    @property
    def effective_coverage(self):
        """Percent the insurer pays: the member's plan, else the scheme default."""
        if self.coverage_percent is not None:
            return self.coverage_percent
        return self.hmo.coverage_percent

    @property
    def is_valid(self):
        """Active and inside its validity window today."""
        today = timezone.localdate()
        if not self.is_active:
            return False
        if self.valid_from and self.valid_from > today:
            return False
        return not (self.valid_to and self.valid_to < today)


class Sale(TenantOwnedModel):
    """One dispensing event: what left the shelf, at what price, paid how.

    Money splits two ways and the two must always agree:
    ``total = patient_payable + hmo_payable``. A cash sale has an empty HMO
    side; an insured sale splits by the member's coverage. The patient side is
    what ``amount_paid`` settles; the HMO side is chased through a ``Claim``.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash"
        CARD = "card"
        TRANSFER = "transfer"
        HMO = "hmo"  # insurer-covered; a co-payment may still be due

    class Status(models.TextChoices):
        PENDING = "pending"    # dispensed, patient side not settled
        PAID = "paid"
        CANCELLED = "cancelled"

    reference = models.CharField(max_length=30)
    # Walk-in sales have no patient. An insured sale always does - the claim
    # needs someone to name (enforced by the serializer).
    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    prescription = models.ForeignKey(
        "analytics.Prescription", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    enrollment = models.ForeignKey(
        HmoEnrollment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sales",
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    patient_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    hmo_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    served_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_sales",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "payment_method"]),
        ]

    def __str__(self):
        return f"{self.reference} ({self.total})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SL{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def balance_due(self):
        """What the patient still owes. Never negative - an overpayment is
        change given, not a debt owed back through this field."""
        return max(_money(self.patient_payable - self.amount_paid), Decimal("0.00"))

    @property
    def coverage_percent(self):
        """Insurer's share of this sale, 0 when it isn't an insured sale."""
        if self.payment_method != self.PaymentMethod.HMO or not self.enrollment_id:
            return Decimal("0.00")
        return Decimal(self.enrollment.effective_coverage)

    # --- dispensing ------------------------------------------------------
    def add_line(self, item, quantity, *, unit_price=None, discount=Decimal("0.00"),
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
                    quantity=take, unit_price=price,
                    # The line discount is charged once, against the first batch
                    # drawn, not repeated per batch.
                    discount=_money(discount) if not lines else Decimal("0.00"),
                    cost_price=batch.cost_price,
                ))
                StockMovement.all_objects.create(
                    tenant=self.tenant, item=item, batch=batch, sale=self,
                    kind=StockMovement.Kind.DISPENSE, quantity=-take, user=user,
                    reason=f"Sale {self.reference}",
                )
                remaining -= take
            self.recalculate()
        return lines

    def recalculate(self):
        """Re-derive every money field from the lines. Cheap, so call it freely.

        The patient/HMO split is computed here rather than stored per line: the
        insurer covers a percentage of the bill, not of individual drugs.
        """
        subtotal = Decimal("0.00")
        discount = Decimal("0.00")
        for line in SaleItem.all_objects.filter(sale=self):
            subtotal += line.gross
            discount += line.discount
        total = _money(max(subtotal - discount, Decimal("0.00")))
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

    def record_payment(self, amount):
        """Take money for the patient's side; mark PAID once it is covered."""
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("Payment must be positive.")
        if self.status == self.Status.CANCELLED:
            raise ValueError("A cancelled sale cannot take payment.")
        self.amount_paid = _money(self.amount_paid + amount)
        if self.amount_paid >= self.patient_payable:
            self.status = self.Status.PAID
        self.save(update_fields=["amount_paid", "status", "updated_at"])
        return self

    def cancel(self, *, reason="", user=None):
        """Reverse the sale: every dispensed unit goes back to its own batch.

        Stock returns to the batch it came from (not to any batch), each with a
        RETURN movement, and an open claim is cancelled with it. The sale rows
        stay - a cancelled sale is history, not a hole in the numbering.
        """
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
            self.status = self.Status.CANCELLED
            self.save(update_fields=["status", "updated_at"])
        return self


class SaleItem(TenantOwnedModel):
    """One batch's worth of one item on a sale.

    ``cost_price`` is copied from the batch at dispensing time so margin
    reporting stays true after the item's price list moves on.
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="sale_lines"
    )
    batch = models.ForeignKey(
        StockBatch, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sale_lines",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return f"{self.quantity} x {self.item_id} @ {self.unit_price}"

    @property
    def gross(self):
        return _money(self.unit_price * self.quantity)

    @property
    def line_total(self):
        return _money(max(self.gross - self.discount, Decimal("0.00")))

    @property
    def margin(self):
        return _money(self.line_total - self.cost_price * self.quantity)


class Claim(TenantOwnedModel):
    """The insurer's share of one sale, from submission to settlement.

    One claim per sale (the sale is the billable event). Amounts are kept
    separately at each stage - claimed, approved, paid - because they differ:
    an HMO routinely approves less than was claimed, and pays less than it
    approved. Nothing here overwrites the sale's own figures.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
        PAID = "paid"
        CANCELLED = "cancelled"

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="claim")
    hmo = models.ForeignKey(HMO, on_delete=models.PROTECT, related_name="claims")
    enrollment = models.ForeignKey(
        HmoEnrollment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="claims",
    )
    # Set when the claim is bundled into a monthly submission (see ClaimBatch).
    batch = models.ForeignKey(
        "pharmacy.ClaimBatch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="claims",
    )
    reference = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_approved = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["tenant", "hmo"]),
        ]

    # What a monthly schedule may still collect. A claim sent on its own — the
    # auto-submitting insurers — belongs on the schedule too: that is the
    # document the remittance is read against. Approved, paid and cancelled
    # claims are past the point where bundling means anything.
    BATCHABLE = (Status.DRAFT, Status.REJECTED, Status.SUBMITTED)

    def __str__(self):
        return f"{self.reference} ({self.status}: {self.amount})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"CL{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def outstanding(self):
        """Approved money not yet received."""
        return max(_money(self.amount_approved - self.amount_paid), Decimal("0.00"))

    # Which status a transition may start from. A rejected claim can be
    # corrected and resent; the rest move in one direction only.
    _ALLOWED = {
        "submit": {Status.DRAFT, Status.REJECTED},
        "approve": {Status.SUBMITTED},
        "reject": {Status.SUBMITTED},
        "pay": {Status.APPROVED},
    }

    def _guard(self, action):
        if self.status not in self._ALLOWED[action]:
            raise ValueError(
                f"Cannot {action} a claim that is {self.get_status_display()}."
            )

    def submit(self):
        """Send to the insurer."""
        self._guard("submit")
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "submitted_at", "rejection_reason",
                                 "updated_at"])
        return self

    def approve(self, amount=None):
        """Insurer accepts it, possibly for less than was claimed."""
        self._guard("approve")
        approved = _money(amount if amount is not None else self.amount)
        if approved < 0 or approved > self.amount:
            raise ValueError(
                "Approved amount must be between 0 and the amount claimed."
            )
        self.status = self.Status.APPROVED
        self.amount_approved = approved
        self.save(update_fields=["status", "amount_approved", "updated_at"])
        return self

    def reject(self, reason=""):
        self._guard("reject")
        self.status = self.Status.REJECTED
        self.amount_approved = Decimal("0.00")
        self.rejection_reason = reason[:255]
        self.save(update_fields=["status", "amount_approved", "rejection_reason",
                                 "updated_at"])
        return self

    def record_payment(self, amount):
        """Bank a remittance. Part-payment leaves the claim APPROVED and open."""
        self._guard("pay")
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("Payment must be positive.")
        self.amount_paid = _money(self.amount_paid + amount)
        fields = ["amount_paid", "updated_at"]
        if self.amount_paid >= self.amount_approved:
            self.status = self.Status.PAID
            self.settled_at = timezone.now()
            fields += ["status", "settled_at"]
        self.save(update_fields=fields)
        return self


def claim_for_sale(sale):
    """Raise the insurer's claim for a sale, or None when nothing is covered.

    Idempotent: a sale already claimed returns its existing claim rather than
    billing the HMO twice.
    """
    if sale.payment_method != Sale.PaymentMethod.HMO or not sale.enrollment_id:
        return None
    if sale.hmo_payable <= 0:
        return None
    existing = Claim.all_objects.filter(sale=sale).first()
    if existing:
        return existing
    claim = Claim.all_objects.create(
        tenant=sale.tenant, sale=sale, hmo_id=sale.enrollment.hmo_id,
        enrollment=sale.enrollment, amount=sale.hmo_payable,
    )
    if claim.hmo.auto_submit_claims:
        claim.submit()
    return claim


class ClaimBatch(TenantOwnedModel):
    """A month's claims bundled into one submission to one insurer.

    HMOs are billed on a cycle, not per sale: the pharmacy sends a schedule and
    gets back one remittance for the lot. The batch is that envelope. Money
    still settles per claim — a remittance is allocated across the claims in it
    — so a part-paid batch says exactly which claims are still short.
    """

    class Status(models.TextChoices):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        PAID = "paid"
        CANCELLED = "cancelled"

    reference = models.CharField(max_length=30)
    hmo = models.ForeignKey(HMO, on_delete=models.PROTECT, related_name="batches")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"{self.reference} ({self.hmo_id}: {self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"CB{uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def _claims(self):
        return Claim.all_objects.filter(batch=self).order_by("id")

    @property
    def totals(self):
        """Claimed, approved and paid across the batch, plus what is still owed."""
        agg = self._claims().exclude(status=Claim.Status.CANCELLED).aggregate(
            claims=models.Count("id"), claimed=models.Sum("amount"),
            approved=models.Sum("amount_approved"), paid=models.Sum("amount_paid"),
        )
        zero = Decimal("0.00")
        approved = _money(agg["approved"] or zero)
        paid = _money(agg["paid"] or zero)
        return {
            "claims": agg["claims"] or 0,
            "claimed": _money(agg["claimed"] or zero),
            "approved": approved,
            "paid": paid,
            "outstanding": max(approved - paid, zero),
        }

    def add_claims(self, claims):
        """Put claims in this batch. Returns how many moved.

        Only unbatched claims for this batch's insurer that are still open are
        taken — one already in another month's envelope, or already decided, is
        left where it is. A claim sent on its own still joins: it is the same
        month's money, and the insurer reconciles against the schedule.
        """
        if self.status != self.Status.DRAFT:
            raise ValueError("Only a draft batch can take more claims.")
        ids = [c.pk for c in claims]
        return Claim.all_objects.filter(
            pk__in=ids, hmo_id=self.hmo_id, batch__isnull=True,
            status__in=Claim.BATCHABLE,
        ).update(batch=self)

    def submit(self):
        """Send the schedule: the batch and every claim on it go out together."""
        if self.status != self.Status.DRAFT:
            raise ValueError("Only a draft batch can be submitted.")
        if not self._claims().exists():
            raise ValueError("The batch has no claims to submit.")
        # Claims already out with the insurer ride along without being sent
        # twice; the schedule is the covering document for all of them.
        claims = list(self._claims().filter(
            status__in=(Claim.Status.DRAFT, Claim.Status.REJECTED)
        ))
        with transaction.atomic():
            for claim in claims:
                claim.submit()
            self.status = self.Status.SUBMITTED
            self.submitted_at = timezone.now()
            self.save(update_fields=["status", "submitted_at", "updated_at"])
        return self

    def approve_all(self):
        """Insurer accepted the schedule in full — approve every claim on it.

        A partial acceptance is not this: approve or reject the individual
        claims instead, then the batch follows what its claims say.
        """
        if self.status != self.Status.SUBMITTED:
            raise ValueError("Only a submitted batch can be approved.")
        with transaction.atomic():
            for claim in self._claims().filter(status=Claim.Status.SUBMITTED):
                claim.approve()
            self.status = self.Status.APPROVED
            self.save(update_fields=["status", "updated_at"])
        return self

    def record_payment(self, amount):
        """Spread one remittance across the batch, oldest claim first.

        Insurers pay a batch, not a claim, so the money is allocated here: each
        approved claim takes what it is still owed until the remittance runs
        out. Paying more than the batch is owed is refused rather than parked
        somewhere unaccounted.
        """
        remaining = _money(amount)
        if remaining <= 0:
            raise ValueError("Payment must be positive.")
        if self.status not in (self.Status.SUBMITTED, self.Status.APPROVED):
            raise ValueError("Only a submitted or approved batch can be paid.")
        outstanding = self.totals["outstanding"]
        if remaining > outstanding:
            raise ValueError(
                f"The batch is only owed {outstanding}; that remittance is larger."
            )
        with transaction.atomic():
            for claim in self._claims().filter(status=Claim.Status.APPROVED):
                if remaining <= 0:
                    break
                take = min(claim.outstanding, remaining)
                if take <= 0:
                    continue
                claim.record_payment(take)
                remaining -= take
            if self.totals["outstanding"] == 0:
                self.status = self.Status.PAID
                self.save(update_fields=["status", "updated_at"])
        return self

    def cancel(self):
        """Withdraw the schedule. Claims are released back to stand alone."""
        if self.status == self.Status.PAID:
            raise ValueError("A paid batch cannot be cancelled.")
        with transaction.atomic():
            self._claims().update(batch=None)
            self.status = self.Status.CANCELLED
            self.save(update_fields=["status", "updated_at"])
        return self
