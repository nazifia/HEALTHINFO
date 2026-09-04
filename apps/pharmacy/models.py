"""HMO cover and the claims raised against it.

Stock, sales, tills and orders now live in ``apps.inventory`` and ``apps.pos``,
which is the layout PharmApp uses. What stays here is the part PharmApp has no
equivalent of: an insurer, a patient's membership of one, and the claim that
follows a covered sale from submission to settlement.

Everything is tenant-owned: one pharmacy never sees another's claims.

Names that moved are re-exported at the bottom of this module, so
``from apps.pharmacy.models import StockItem`` still resolves. New code should
import from the owning app.
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

    sale = models.OneToOneField(
        "pos.Sale", on_delete=models.CASCADE, related_name="claim"
    )
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
    from apps.pos.models import Sale

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
        verbose_name_plural = "claim batches"
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
        if not self._claims().exclude(status=Claim.Status.CANCELLED).exists():
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


# --- moved models, re-exported ------------------------------------------
# ponytail: one import line each so callers written against the old layout —
# the seed command, the tests, anything downstream — keep working. Delete a
# name from here once nothing imports it from this module.
from apps.inventory.models import (  # noqa: E402,F401  (re-export)
    OutOfStock,
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Supplier,
    TransferRequest,
    adjust_stock,
    receive_stock,
    take_stock,
)
from apps.pos.models import (  # noqa: E402,F401  (re-export)
    Cashier,
    DispensingLog,
    Expense,
    ExpenseCategory,
    Notification,
    PaymentRequest,
    PaymentRequestItem,
    PurchaseOrder,
    PurchaseOrderLine,
    ReturnRecord,
    Sale,
    SaleItem,
    SalePayment,
    TillSession,
    receive_purchase_line,
    record_return,
)
