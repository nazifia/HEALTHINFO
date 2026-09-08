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

from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

from apps.governance.models import AuditLog
from apps.tenants.models import TenantOwnedModel
from config.money import money as _money


def _audit(obj, user, from_status, to_status, note=""):
    """Append-only note of who moved this record, and why.

    Every other transition leaves its mark on the record itself - the code, the
    amount, the reason. Undoing one erases exactly that, so the undo is the
    transition that has to be written down somewhere else.
    """
    AuditLog.objects.create(
        tenant_id=obj.tenant_id, user=user,
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk,
        from_status=from_status, to_status=to_status, note=note[:1000],
    )


def notify_scheme_change(rule, title, message, by=None):
    """Tell the two sides of a contract that its price list moved.

    A sale prices itself off these rows, so the counter has to hear about a
    change it did not make — and an insurer has to hear when the pharmacy
    admin keeps the list on its behalf. Whoever made the change is left out:
    they were the one typing.
    """
    from apps.accounts.models import Role, User
    from apps.pos.models import Notification

    audience = User.objects.filter(
        tenant_id=rule.tenant_id, is_active=True
    ).filter(
        models.Q(role__in=(Role.TENANT_ADMIN, Role.PHARMACIST))
        | models.Q(role=Role.HMO, hmo_id=rule.hmo_id)
    )
    if by is not None and by.pk:
        audience = audience.exclude(pk=by.pk)
    Notification.objects.bulk_create([
        Notification(
            tenant_id=rule.tenant_id, user=user,
            kind=Notification.Kind.SYSTEM,
            priority=Notification.Priority.MEDIUM,
            title=title[:200], message=message,
        )
        for user in audience
    ])



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
    # Per-drug cover lives in ``HmoItemRule``; anything with no rule of its own
    # is covered at ``coverage_percent``.
    #
    # Insured amount above which this HMO wants to clear the sale before it
    # happens. 0 (the default) asks for no authorisation, ever.
    preauth_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "name")
        verbose_name = "HMO"

    def __str__(self):
        return self.name


class HmoItemRule(TenantOwnedModel):
    """One line of a scheme's price list: what it pays for one particular drug.

    A contract rarely covers everything at one rate: antimalarials at 100,
    branded alternatives at 50, supplements at nothing. ``coverage_percent``
    of 0 is the exclusion — the drug falls entirely to the patient even on a
    covered sale. A drug with no rule is covered at the scheme's default.

    ``tariff`` is the other half of the list: the scheme's own unit price,
    which caps what the percentage is taken of. The insurer keeps these rows
    itself (see ``HmoItemRuleViewSet``), so a contract change is entered by
    the party that agreed it rather than retyped by the pharmacy.
    """

    hmo = models.ForeignKey(HMO, on_delete=models.CASCADE,
                            related_name="item_rules")
    item = models.ForeignKey("inventory.StockItem", on_delete=models.CASCADE,
                             related_name="hmo_rules")
    coverage_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    # The scheme's own price for this drug: the most it reimburses for one
    # unit, whatever the pharmacy charges. NULL is no ceiling - the shelf
    # price is covered at ``coverage_percent``. A pharmacy pricing above the
    # tariff is not refused the sale; the excess simply stays with the patient.
    tariff = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("item__name", "id")
        unique_together = ("tenant", "hmo", "item")
        indexes = [models.Index(fields=["tenant", "hmo"])]

    def __str__(self):
        return f"{self.item_id} @ {self.coverage_percent}%"


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
    # Most a member's plan pays out in a calendar year. Blank is uncapped; once
    # the cap is reached cover stops mid-sale and the patient pays the rest.
    annual_limit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
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

    def used_this_year(self, exclude_sale=None):
        """Insured money already claimed for this member this calendar year.

        A cancelled claim never cost the insurer anything, so it frees the
        benefit back up. ``exclude_sale`` keeps a sale's own claim out of the
        sum while that sale is still being priced.
        """
        claims = Claim.all_objects.filter(
            enrollment=self, created_at__year=timezone.localdate().year
        ).exclude(status=Claim.Status.CANCELLED)
        if exclude_sale is not None and exclude_sale.pk:
            claims = claims.exclude(sale=exclude_sale)
        return _money(claims.aggregate(models.Sum("amount"))["amount__sum"] or 0)

    def remaining_benefit(self, exclude_sale=None):
        """What is left of the annual limit, or None when the plan is uncapped."""
        if self.annual_limit is None:
            return None
        used = self.used_this_year(exclude_sale=exclude_sale)
        return max(_money(self.annual_limit - used), Decimal("0.00"))


class PreAuthorization(TenantOwnedModel):
    """The insurer's clearance for one covered sale, asked for before dispensing.

    Above ``HMO.preauth_threshold`` the scheme wants to see the bill before the
    drug leaves the shelf. The pharmacy raises a request, the insurer answers
    with a code and the amount they will stand behind, and the counter spends
    that answer on exactly one sale. Keeping it as a record rather than a typed
    code is what lets a refusal, an expiry, or an approval for less than was
    asked be told apart afterwards.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested"
        APPROVED = "approved"
        DECLINED = "declined"
        USED = "used"
        CANCELLED = "cancelled"

    reference = models.CharField(max_length=30)
    hmo = models.ForeignKey(HMO, on_delete=models.PROTECT, related_name="preauths")
    enrollment = models.ForeignKey(
        HmoEnrollment, on_delete=models.CASCADE, related_name="preauths"
    )
    # Who asked. The insurer's answer is told back to them, and a request
    # outlives the account that raised it.
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="preauth_requests",
    )
    # What the pharmacy expects to bill the insurer for this basket.
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # What they agreed to stand behind, which can be less than was asked.
    amount_approved = models.DecimalField(max_digits=12, decimal_places=2,
                                          default=0)
    # The insurer's own reference, quoted back on the claim.
    code = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.REQUESTED)
    # Clearances go stale: an approval given in March does not cover a sale in
    # June. Blank means it does not expire.
    expires_on = models.DateField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    # How often the recorded answer was withdrawn. A request answered once and
    # left alone reads 0; anything else is worth a second look before the
    # insurer is billed against it.
    reopened_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "pre-authorization"
        ordering = ("-created_at", "-id")
        unique_together = ("tenant", "reference")
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"{self.reference} ({self.status}: {self.amount_approved})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"PA{uuid4().hex[:10].upper()}"
        if not self.hmo_id and self.enrollment_id:
            self.hmo_id = self.enrollment.hmo_id
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return bool(self.expires_on and self.expires_on < timezone.localdate())

    @property
    def is_usable(self):
        """Approved, still in date, and not already spent on a sale."""
        return self.status == self.Status.APPROVED and not self.is_expired

    def _notify(self, title, message):
        """Tell whoever raised the request what the insurer said.

        They are usually at the till with a waiting patient, so the answer goes
        to them rather than waiting on someone reloading the request page.
        """
        if not self.requested_by_id:
            return
        from apps.pos.models import Notification  # local: pos is imported below

        Notification.objects.create(
            tenant_id=self.tenant_id, user_id=self.requested_by_id,
            kind=Notification.Kind.SYSTEM, priority=Notification.Priority.HIGH,
            title=title[:200], message=message,
        )

    _ALLOWED = {
        "approve": {Status.REQUESTED},
        "decline": {Status.REQUESTED},
        "cancel": {Status.REQUESTED, Status.APPROVED},
        # An answer is typed by hand and can be typed wrong. It is undone
        # until it has been spent on a sale, after which the goods are gone
        # and a fresh request is the only honest way back.
        "reopen": {Status.APPROVED, Status.DECLINED},
    }

    def _guard(self, action):
        if self.status not in self._ALLOWED[action]:
            raise ValueError(
                f"Cannot {action} a request that is {self.get_status_display()}."
            )

    def approve(self, *, code="", amount=None, expires_on=None):
        """Record the insurer's clearance, for all or part of what was asked."""
        self._guard("approve")
        approved = _money(amount if amount is not None else self.amount)
        if approved <= 0:
            raise ValueError("An approved amount must be positive.")
        self.status = self.Status.APPROVED
        self.amount_approved = approved
        self.code = code[:60]
        self.expires_on = expires_on or self.expires_on
        self.decided_at = timezone.now()
        self.reason = ""
        self.save(update_fields=["status", "amount_approved", "code",
                                 "expires_on", "decided_at", "reason",
                                 "updated_at"])
        self._notify(f"{self.reference} authorised",
                     f"{self.hmo.name} will stand behind {approved}. "
                     f"Dispense against {self.reference}.")
        return self

    def decline(self, reason=""):
        self._guard("decline")
        self.status = self.Status.DECLINED
        self.amount_approved = Decimal("0.00")
        self.reason = reason[:255]
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "amount_approved", "reason",
                                 "decided_at", "updated_at"])
        self._notify(f"{self.reference} declined",
                     reason or "The insurer refused the request.")
        return self

    def cancel(self, reason=""):
        """Withdraw the request - the sale was not made after all."""
        self._guard("cancel")
        self.status = self.Status.CANCELLED
        if reason:
            self.reason = reason[:255]
        self.save(update_fields=["status", "reason", "updated_at"])
        self._notify(f"{self.reference} withdrawn",
                     reason or "The request was withdrawn before an answer.")
        return self

    def reopen(self, reason="", by=None):
        """Undo the recorded answer, putting the request back to unanswered.

        The decision guards refuse to answer a request twice, which is what a
        wrong amount or a mistyped code would otherwise be stuck behind. This
        clears the answer so the right one can be recorded; it does not decide
        anything itself.

        ``by`` is whoever withdrew it. The answer being erased was money the
        pharmacy could have billed, so the trail says who erased it.
        """
        self._guard("reopen")
        was, was_amount = self.status, self.amount_approved
        self.reopened_count += 1
        self.status = self.Status.REQUESTED
        self.amount_approved = Decimal("0.00")
        self.code = ""
        self.expires_on = None
        self.decided_at = None
        self.reason = reason[:255]
        self.save(update_fields=["status", "amount_approved", "code",
                                 "expires_on", "decided_at", "reason",
                                 "reopened_count", "updated_at"])
        _audit(self, by, was, self.Status.REQUESTED,
               f"Withdrew an answer of {was_amount}."
               + (f" {reason}" if reason else ""))
        self._notify(f"{self.reference} reopened",
                     reason or "The answer recorded against this request was "
                     "withdrawn. It is waiting on the insurer again.")
        return self

    def mark_used(self):
        """Spend the clearance. One approval covers one sale, not a standing
        licence to bill the insurer."""
        if self.status != self.Status.APPROVED:
            raise ValueError("Only an approved request can be used.")
        self.status = self.Status.USED
        self.save(update_fields=["status", "updated_at"])
        return self

    @property
    def item_limits(self):
        """How much of each drug the insurer cleared: ``{item_id: quantity}``.

        A refused drug sits here as 0, a part-cleared one as the quantity the
        insurer stood behind. Empty when the request was not itemised, which
        keeps a lump-sum request out of the counter's way.
        """
        return dict(
            PreAuthorizationItem.all_objects.filter(authorization=self).exclude(
                status=PreAuthorizationItem.Status.REQUESTED
            ).values_list("item_id", "quantity_approved")
        )

    def settle_from_items(self):
        """Answer the request itself once every medication on it is decided.

        The insurer decides drug by drug; the request as a whole is whatever
        those decisions add up to. Anything still undecided leaves the request
        open, so a half-answered request never clears a sale.
        """
        items = list(PreAuthorizationItem.all_objects.filter(authorization=self))
        if not items or any(i.status == PreAuthorizationItem.Status.REQUESTED
                            for i in items):
            return self
        approved = _money(sum((i.amount_approved for i in items), Decimal("0.00")))
        if approved > 0:
            return self.approve(code=self.code, amount=approved,
                                expires_on=self.expires_on)
        return self.decline("Every medication on the request was declined.")


class PreAuthorizationItem(TenantOwnedModel):
    """One ordered medication on an authorisation request, decided on its own.

    Insurers answer a request drug by drug: the antibiotic is cleared, the
    branded painkiller on the same script is not. Keeping each line's answer
    here is what lets the counter dispense the cleared drugs and turn the
    patient away for the rest, rather than losing the whole basket to one
    refusal.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested"
        APPROVED = "approved"
        DECLINED = "declined"

    authorization = models.ForeignKey(
        PreAuthorization, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey("inventory.StockItem", on_delete=models.PROTECT,
                             related_name="preauth_items")
    quantity = models.PositiveIntegerField(default=1)
    # How much of that the insurer stood behind - they cut a quantity, 20 of
    # the 30 tablets asked for, as readily as they cut an amount.
    quantity_approved = models.PositiveIntegerField(default=0)
    # What the pharmacy expects to bill the insurer for this drug.
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_approved = models.DecimalField(max_digits=12, decimal_places=2,
                                          default=0)
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.REQUESTED)
    reason = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("id",)
        unique_together = ("authorization", "item")
        indexes = [models.Index(fields=["tenant", "authorization"])]

    def __str__(self):
        return f"{self.quantity} x {self.item_id} ({self.status})"

    def _guard(self):
        if self.status != self.Status.REQUESTED:
            raise ValueError(
                f"That medication is already {self.get_status_display()}."
            )

    def approve(self, amount=None, quantity=None):
        """Clear this drug, for all or part of what was asked for it.

        An insurer cutting the quantity - 20 of the 30 tablets - cuts the bill
        with it, so an unstated amount follows the cleared quantity pro rata
        rather than standing behind the whole ask.
        """
        self._guard()
        cleared = int(quantity) if quantity is not None else self.quantity
        if not 0 < cleared <= self.quantity:
            raise ValueError(
                f"The insurer can clear 1 to {self.quantity} of that medication."
            )
        if amount is not None:
            approved = _money(amount)
        else:
            approved = _money(self.amount * cleared / (self.quantity or 1))
        if approved <= 0:
            raise ValueError("An approved amount must be positive.")
        self.status = self.Status.APPROVED
        self.amount_approved = approved
        self.quantity_approved = cleared
        self.reason = ""
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "amount_approved", "quantity_approved",
                                 "reason", "decided_at", "updated_at"])
        self.authorization.settle_from_items()
        return self

    def decline(self, reason=""):
        """Refuse this drug. The pharmacy does not dispense it under cover."""
        self._guard()
        self.status = self.Status.DECLINED
        self.amount_approved = Decimal("0.00")
        self.quantity_approved = 0
        self.reason = reason[:255]
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "amount_approved", "quantity_approved",
                                 "reason", "decided_at", "updated_at"])
        self.authorization.settle_from_items()
        return self

    def reopen(self, reason="", by=None):
        """Undo the recorded answer to this medication.

        The request settled the moment its last medication was decided, so a
        line going back to unanswered takes the request with it - otherwise a
        corrected line would sit under a total that no longer adds up.
        """
        if self.status == self.Status.REQUESTED:
            raise ValueError("That medication is still awaiting the insurer.")
        auth = self.authorization
        if auth.status == PreAuthorization.Status.USED:
            raise ValueError(
                "That clearance was already spent on a sale. Raise a new request."
            )
        was, was_amount = self.status, self.amount_approved
        self.status = self.Status.REQUESTED
        self.amount_approved = Decimal("0.00")
        self.quantity_approved = 0
        self.reason = reason[:255]
        self.decided_at = None
        self.save(update_fields=["status", "amount_approved", "quantity_approved",
                                 "reason", "decided_at", "updated_at"])
        _audit(self, by, was, self.Status.REQUESTED,
               f"Withdrew an answer of {was_amount} on {self.item}."
               + (f" {reason}" if reason else ""))
        if auth.status in (PreAuthorization.Status.APPROVED,
                           PreAuthorization.Status.DECLINED):
            auth.reopen(reason, by=by)
        return self


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
        # Anything the pharmacy can still stop billing for. Money already
        # banked is not withdrawn by editing a status.
        "cancel": {Status.DRAFT, Status.SUBMITTED, Status.REJECTED,
                   Status.APPROVED},
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

    def cancel(self, reason=""):
        """Stop billing for this claim and drop it off any schedule.

        A cancelled claim costs the insurer nothing, so it also gives the
        member's annual benefit back (see ``HmoEnrollment.used_this_year``).
        """
        self._guard("cancel")
        self.status = self.Status.CANCELLED
        self.batch = None
        if reason:
            self.rejection_reason = reason[:255]
        self.save(update_fields=["status", "batch", "rejection_reason",
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
