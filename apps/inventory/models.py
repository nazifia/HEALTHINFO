"""Inventory: what is on the shelf, where it came from, and where it went.

* ``StockItem`` is a line on the price list — a drug or a consumable, held in
  one of two stores (retail or wholesale) and optionally at one branch.
* ``StockBatch`` is a physical consignment of it, with its own expiry and cost.
* ``StockMovement`` is the append-only trail of every unit in or out. Batch
  quantity is the fast read; the movement rows are the audit that explains it.
* ``StockCheck`` is a counted stocktake: expected against actual, approved
  line by line, each correction landing as an ADJUSTMENT movement.
* ``TransferRequest`` moves stock between the retail and wholesale stores,
  which are two item rows, not one.

Everything is tenant-owned: one pharmacy never sees another's stock or costs.

ponytail: the tables keep their original ``pharmacy_*`` names (``db_table``
below). The models moved app; the rows did not, so there is no data migration
to get wrong. Rename them only if you are willing to write one.
"""
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.tenants.models import TenantOwnedModel

MONEY = Decimal("0.01")


def _money(value):
    """Round to kobo. Every stored amount goes through this."""
    return Decimal(value).quantize(MONEY)


class Store(models.TextChoices):
    """Which counter an item is dispensed from. Retail sells units, wholesale
    sells packs, and the same drug is a separate row in each."""

    RETAIL = "retail"
    WHOLESALE = "wholesale"


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
        db_table = "pharmacy_supplier"
        ordering = ("name", "id")
        unique_together = ("tenant", "name")

    def __str__(self):
        return self.name


class StockItem(TenantOwnedModel):
    """Something the pharmacy holds and sells - a drug or a consumable.

    ``medication`` links to the shared catalog when there is a match, so stock
    and prescriptions talk about the same drug; it stays optional because
    gloves and syringes are inventory too and are in no drug catalog.
    """

    class Form(models.TextChoices):
        # ponytail: values stay lowercase because rows already carry them.
        # The list is PharmApp's dosage forms, folded to this project's casing.
        TABLET = "tablet"
        CAPSULE = "capsule"
        SYRUP = "syrup"
        INJECTION = "injection"
        INFUSION = "infusion"
        INHALER = "inhaler"
        SUSPENSION = "suspension"
        SOLUTION = "solution"
        CREAM = "cream"
        PASTE = "paste"
        PATCH = "patch"
        GALENICAL = "galenical"
        DROPS = "drops"
        EYE_DROP = "eye_drop", "Eye drop"
        EAR_DROP = "ear_drop", "Ear drop"
        EYE_OINTMENT = "eye_ointment", "Eye ointment"
        RECTAL = "rectal"
        VAGINAL = "vaginal"
        CONSUMABLE = "consumable"
        DETERGENT = "detergent"
        SOAP = "soap"
        DRINK = "drink"
        TABLE_WATER = "table_water", "Table water"
        FOOD_ITEM = "food_item", "Food item"
        BISCUIT = "biscuit"
        SWEET = "sweet"
        OTHER = "other"

    class BarcodeType(models.TextChoices):
        UPC = "UPC"
        EAN13 = "EAN13", "EAN-13"
        CODE128 = "CODE128", "Code 128"
        QR = "QR", "QR code"
        OTHER = "OTHER", "Other"

    medication = models.ForeignKey(
        "catalog.Medication", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_items",
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="items",
        help_text="Branch holding this line. Blank means tenant-wide.",
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=200, blank=True)
    sku = models.CharField(max_length=50, blank=True)
    form = models.CharField(max_length=20, choices=Form.choices, default=Form.TABLET)
    # What one sold unit is ("tablet", "bottle of 100ml"). Prices are per unit.
    unit = models.CharField(max_length=50, default="unit")
    store = models.CharField(
        max_length=20, choices=Store.choices, default=Store.RETAIL
    )
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Percent added to cost to reach the shelf price. Applied once, when the
    # row is created — after that the price is whatever it was last set to,
    # because a repriced item must not silently move when its cost does.
    markup = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # Stock at or below this is "low" - the reorder signal the admin dashboard
    # and the low-stock endpoint read.
    reorder_level = models.PositiveIntegerField(default=0)
    barcode = models.CharField(max_length=100, blank=True, db_index=True)
    barcode_type = models.CharField(
        max_length=20, choices=BarcodeType.choices, blank=True
    )
    gtin = models.CharField(max_length=50, blank=True)
    prescription_only = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "pharmacy_stockitem"
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
            models.Index(fields=["tenant", "store"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self._state.adding and self.markup and not self.unit_price:
            self.unit_price = _money(
                Decimal(self.cost_price)
                * (Decimal("100") + Decimal(self.markup))
                / Decimal("100")
            )
        super().save(*args, **kwargs)

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
        db_table = "pharmacy_stockbatch"
        verbose_name_plural = "stock batches"
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
        TRANSFER = "transfer"      # moved between the retail and wholesale stores

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
        "pos.Sale", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="movements",
    )
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "pharmacy_stockmovement"
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
                  cost_price=None, supplier=None, user=None,
                  kind=StockMovement.Kind.RECEIPT, reason=None):
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
            kind=kind, quantity=quantity, user=user,
            reason=reason or (f"Received from {supplier.name}" if supplier
                              else "Stock received"),
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


def take_stock(item, quantity, *, kind, reason, user=None, sale=None):
    """Draw units off an item first-expiry-first-out. Returns the batches hit.

    The one door out of stock that is not a sale line: a transfer to the other
    store, or a write-off spread across consignments. Nothing is committed if
    the shelf cannot cover the request.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")
    taken = []
    with transaction.atomic():
        batches = list(item.sellable_batches().select_for_update())
        available = sum(b.quantity for b in batches)
        if available < quantity:
            raise OutOfStock(item, quantity, available)
        remaining = quantity
        for batch in batches:
            if remaining <= 0:
                break
            take = min(batch.quantity, remaining)
            batch.quantity -= take
            batch.save(update_fields=["quantity", "updated_at"])
            StockMovement.all_objects.create(
                tenant=item.tenant, item=item, batch=batch, sale=sale,
                kind=kind, quantity=-take, user=user, reason=reason,
            )
            taken.append((batch, take))
            remaining -= take
    return taken


class StockCheck(TenantOwnedModel):
    """A stocktake: what the books say against what was counted.

    Lines are entered as they are counted and approved one by one, because a
    count is agreed item by item. Approving a line writes the correction as an
    ADJUSTMENT movement, so a discrepancy is on the ledger rather than being
    quietly typed over.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    store = models.CharField(
        max_length=20, choices=Store.choices, default=Store.RETAIL
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_checks",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="stock_checks",
    )
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_stock_checks",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"Stock check {self.pk} ({self.store}: {self.status})"

    def _lines(self):
        return StockCheckItem.all_objects.filter(stock_check=self).select_related(
            "item"
        )

    @property
    def totals(self):
        """Lines counted, and what the discrepancy is worth at cost."""
        lines = list(self._lines())
        counted = [line for line in lines if line.actual_quantity is not None]
        return {
            "lines": len(lines),
            "counted": len(counted),
            "discrepancy_units": sum(line.discrepancy for line in counted),
            "discrepancy_value": _money(
                sum(line.cost_difference for line in counted)
            ),
        }

    def complete(self, *, user=None):
        """Apply every counted line, then close the check.

        A line with no count is left alone: not counting something is not the
        same as counting zero, and treating it as zero would write off stock
        nobody looked at.
        """
        if self.status in (self.Status.COMPLETED, self.Status.CANCELLED):
            raise ValueError(f"This stock check is already {self.status}.")
        with transaction.atomic():
            for line in self._lines():
                if line.actual_quantity is None:
                    continue
                line.apply(user=user)
            self.status = self.Status.COMPLETED
            self.approved_by = user
            self.approved_at = timezone.now()
            self.save(update_fields=["status", "approved_by", "approved_at",
                                     "updated_at"])
        return self

    def cancel(self):
        if self.status == self.Status.COMPLETED:
            raise ValueError("A completed stock check cannot be cancelled.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])
        return self


class StockCheckItem(TenantOwnedModel):
    """One counted line: expected, actual, and what was done about the gap."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"   # counted and agreed, nothing to correct
        ADJUSTED = "adjusted"   # counted, and the correction was written

    stock_check = models.ForeignKey(
        StockCheck, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="stock_check_lines"
    )
    expected_quantity = models.IntegerField(default=0)
    actual_quantity = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("id",)
        unique_together = ("stock_check", "item")
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return (f"{self.item_id}: expected {self.expected_quantity}, "
                f"counted {self.actual_quantity}")

    @property
    def discrepancy(self):
        """Counted less expected. Negative is shrinkage."""
        if self.actual_quantity is None:
            return 0
        return self.actual_quantity - self.expected_quantity

    @property
    def cost_difference(self):
        """What the discrepancy cost, at what the stock cost to buy."""
        return _money(Decimal(self.discrepancy) * Decimal(self.item.cost_price))

    def apply(self, *, user=None):
        """Write the correction to stock, oldest batch first.

        A shortfall comes off the batches that would have sold first; a surplus
        goes onto the newest batch, which is where uncounted arrivals sit.
        """
        if self.actual_quantity is None:
            raise ValueError("That line has not been counted yet.")
        delta = self.discrepancy
        if delta == 0:
            self.status = self.Status.APPROVED
            self.save(update_fields=["status", "updated_at"])
            return self
        reason = f"Stock check {self.stock_check_id}"
        with transaction.atomic():
            if delta < 0:
                take_stock(self.item, -delta, kind=StockMovement.Kind.ADJUSTMENT,
                           reason=reason, user=user)
            else:
                batch = (StockBatch.all_objects.filter(item=self.item)
                         .order_by("-id").first())
                if batch is None:
                    batch = StockBatch.all_objects.create(
                        tenant=self.item.tenant, item=self.item,
                        batch_number=f"COUNT-{self.stock_check_id}",
                        quantity=0, quantity_received=0,
                        cost_price=self.item.cost_price,
                    )
                adjust_stock(batch, batch.quantity + delta, reason=reason,
                             user=user)
            self.status = self.Status.ADJUSTED
            self.save(update_fields=["status", "updated_at"])
        return self


class TransferRequest(TenantOwnedModel):
    """Stock asked for from the other store, and what was actually sent.

    Retail and wholesale hold the same drug as two rows, so a transfer is a
    move between two items: units leave ``from_item`` and arrive on
    ``to_item`` as a new batch. Both legs are movements, so neither store's
    ledger has a hole in it.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        RECEIVED = "received"

    from_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="transfers_out"
    )
    to_item = models.ForeignKey(
        StockItem, on_delete=models.PROTECT, related_name="transfers_in"
    )
    requested_quantity = models.PositiveIntegerField(default=1)
    approved_quantity = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="transfer_requests",
    )
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_transfers",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return (f"Transfer {self.pk}: {self.requested_quantity} from item "
                f"{self.from_item_id} to {self.to_item_id} ({self.status})")

    @property
    def direction(self):
        return f"{self.from_item.store} → {self.to_item.store}"

    def approve(self, quantity=None, *, user=None):
        """Agree the move and carry the stock across in one transaction.

        Approving is the move: there is no window where the units are on
        neither shelf. A short approval is normal — the sending store gives
        what it can spare — so the approved quantity is what actually travels.
        """
        if self.status != self.Status.PENDING:
            raise ValueError("Only a pending transfer can be approved.")
        quantity = int(quantity if quantity is not None
                       else self.requested_quantity)
        if quantity <= 0:
            raise ValueError("An approved transfer must move at least one unit.")
        if quantity > self.requested_quantity:
            raise ValueError("More than was asked for is a new request.")
        reason = f"Transfer {self.pk}"
        with transaction.atomic():
            take_stock(self.from_item, quantity,
                       kind=StockMovement.Kind.TRANSFER, reason=reason, user=user)
            receive_stock(
                self.to_item, quantity, batch_number=f"TR{self.pk}",
                cost_price=self.from_item.cost_price, user=user,
                kind=StockMovement.Kind.TRANSFER, reason=reason,
            )
            self.approved_quantity = quantity
            self.approved_by = user
            self.status = self.Status.APPROVED
            self.save(update_fields=["approved_quantity", "approved_by", "status",
                                     "updated_at"])
        return self

    def reject(self, *, user=None, reason=""):
        if self.status != self.Status.PENDING:
            raise ValueError("Only a pending transfer can be rejected.")
        self.status = self.Status.REJECTED
        self.approved_by = user
        if reason:
            self.notes = reason
        self.save(update_fields=["status", "approved_by", "notes", "updated_at"])
        return self

    def receive(self):
        """The receiving store confirms the units arrived on its shelf."""
        if self.status != self.Status.APPROVED:
            raise ValueError("Only an approved transfer can be received.")
        self.status = self.Status.RECEIVED
        self.save(update_fields=["status", "updated_at"])
        return self
