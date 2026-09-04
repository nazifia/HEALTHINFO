"""Prescriptions the pharmacy dispenses against, and what they owe the writer.

This is the counter's prescription: a named prescriber, a list of drugs, and a
line-by-line record of what has actually been handed over. It is not
``analytics.Prescription``, which is a de-identified clinical record for
surveillance — the two answer different questions and neither should be made
to answer the other's.

Two kinds of money flow back to the prescriber:

* a **commission** — a percentage of what the pharmacy sold on their script;
* a **consultation payout** — a flat fee they set, charged silently at the
  till and owed on to them in full.

Both are snapshotted when they are raised, so a later change to a rate or a
price cannot rewrite what was already earned.
"""
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.tenants.models import TenantOwnedModel

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _money(value):
    return Decimal(value).quantize(MONEY)


class Hospital(TenantOwnedModel):
    """A clinic or hospital prescribers write from."""

    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "name")

    def __str__(self):
        return self.name


class Prescriber(TenantOwnedModel):
    """A doctor whose scripts this pharmacy fills.

    ``commission_rate`` is what they earn on what their script sells. The
    consultation bands A–E are fees they set themselves; the pharmacy charges
    one of them at the till and owes it back untouched.
    """

    CONSULT_CATEGORIES = ("A", "B", "C", "D", "E")

    hospital = models.ForeignKey(
        Hospital, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescribers",
    )
    name = models.CharField(max_length=200)
    license_number = models.CharField(max_length=100, blank=True)
    specialty = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    clinic = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    commission_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Percent (0-100) of dispensed sales earned as commission.",
    )
    consult_fee_a = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    consult_fee_b = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    consult_fee_c = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    consult_fee_d = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    consult_fee_e = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ("name", "id")
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "license_number"]),
        ]

    def __str__(self):
        suffix = f" ({self.license_number})" if self.license_number else ""
        return f"{self.name}{suffix}"

    @property
    def consultation_fees(self):
        return {c: self.fee_for(c) for c in self.CONSULT_CATEGORIES}

    def fee_for(self, category):
        """The fee for a band letter, or zero for anything unrecognised."""
        letter = (category or "").strip().upper()
        if letter not in self.CONSULT_CATEGORIES:
            return ZERO
        return _money(getattr(self, f"consult_fee_{letter.lower()}"))

    @property
    def outstanding(self):
        """What this prescriber is still owed, split by what it is owed for."""
        commission = PrescriberCommission.all_objects.filter(
            prescriber=self, status=PrescriberCommission.Status.PENDING
        ).aggregate(t=models.Sum("commission_amount"))["t"] or ZERO
        consultation = ConsultationPayout.all_objects.filter(
            prescriber=self, status=ConsultationPayout.Status.PENDING
        ).aggregate(t=models.Sum("consultation_fee"))["t"] or ZERO
        return {
            "commission": _money(commission),
            "consultation": _money(consultation),
            "total": _money(commission + consultation),
        }


class Prescription(TenantOwnedModel):
    """A script presented at the counter, and how much of it has been filled.

    ``status`` is never set by hand — it follows the lines, because "partly
    dispensed" is a fact about which drugs went out, not a flag someone
    remembers to tick.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        PARTIAL = "partial"
        DISPENSED = "dispensed"
        CANCELLED = "cancelled"

    class Source(models.TextChoices):
        PHARMACY = "pharmacy"   # written up at the counter from a paper script
        PORTAL = "portal"       # sent in by the prescriber

    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions",
    )
    customer = models.ForeignKey(
        "customers.Customer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions",
    )
    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dispensing_prescriptions",
    )
    customer_name = models.CharField(max_length=200, default="Walk-in")
    customer_phone = models.CharField(max_length=20, blank=True)
    prescriber = models.ForeignKey(
        Prescriber, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions",
    )
    # Kept for the scripts that arrive with a name and nothing else on them.
    doctor_name = models.CharField(max_length=200, blank=True)
    diagnosis = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    consultation_category = models.CharField(max_length=1, blank=True)
    # Snapshot of the band's fee when the script was written up: the prescriber
    # may reprice tomorrow, but this is what the patient was charged.
    consultation_fee = models.DecimalField(max_digits=12, decimal_places=2,
                                           default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    source = models.CharField(
        max_length=30, choices=Source.choices, default=Source.PHARMACY
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions_written",
    )
    dispensed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "customer_phone"]),
        ]

    def __str__(self):
        return f"Rx{self.pk} — {self.customer_name} ({self.status})"

    def save(self, *args, **kwargs):
        if (self._state.adding and self.prescriber_id
                and self.consultation_category and not self.consultation_fee):
            self.consultation_fee = self.prescriber.fee_for(
                self.consultation_category
            )
        super().save(*args, **kwargs)

    def _lines(self):
        return PrescriptionItem.all_objects.filter(prescription=self)

    def sync_status(self):
        """Re-derive the status from what has actually been dispensed."""
        if self.status == self.Status.CANCELLED:
            return self
        lines = list(self._lines())
        if not lines:
            return self
        dispensed = sum(1 for line in lines if line.is_dispensed)
        if dispensed == 0:
            status, when = self.Status.PENDING, None
        elif dispensed == len(lines):
            status, when = self.Status.DISPENSED, self.dispensed_at or timezone.now()
        else:
            status, when = self.Status.PARTIAL, self.dispensed_at
        if (status, when) != (self.status, self.dispensed_at):
            self.status = status
            self.dispensed_at = when
            self.save(update_fields=["status", "dispensed_at", "updated_at"])
        return self

    def raise_prescriber_dues(self, sale):
        """Book what the prescriber earned on this sale. Idempotent.

        Commission is a share of what was actually sold, so it is raised per
        sale. The consultation fee is a flat charge for the script, so it is
        raised once however many times the script is part-filled.
        """
        if not self.prescriber_id:
            return None, None
        prescriber = self.prescriber
        commission = None
        rate = Decimal(prescriber.commission_rate)
        if rate > 0 and sale.total > 0:
            commission, _created = PrescriberCommission.all_objects.get_or_create(
                tenant=self.tenant, prescriber=prescriber, prescription=self,
                sale=sale,
                defaults={
                    "patient_name": self.customer_name,
                    "sales_amount": sale.total,
                    "commission_rate": rate,
                    "commission_amount": _money(sale.total * rate / Decimal("100")),
                },
            )
        payout = None
        if self.consultation_fee > 0:
            payout, _created = ConsultationPayout.all_objects.get_or_create(
                tenant=self.tenant, prescription=self,
                defaults={
                    "prescriber": prescriber,
                    "patient_name": self.customer_name,
                    "consultation_category": self.consultation_category,
                    "consultation_fee": self.consultation_fee,
                },
            )
        return commission, payout


class PrescriptionItem(TenantOwnedModel):
    """One drug on a script, and whether it has gone out yet."""

    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        "inventory.StockItem", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescription_lines",
    )
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(max_length=50, default="unit(s)")
    dosage = models.CharField(max_length=200, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    instructions = models.TextField(blank=True)
    is_dispensed = models.BooleanField(default=False)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    dispensed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dispensed_rx_lines",
    )

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["tenant", "item"])]

    def __str__(self):
        return f"{self.name} x{self.quantity} (Rx{self.prescription_id})"

    def mark_dispensed(self, *, user=None):
        """Tick the line off and let the script's status follow."""
        if self.is_dispensed:
            return self
        with transaction.atomic():
            self.is_dispensed = True
            self.dispensed_at = timezone.now()
            self.dispensed_by = user
            self.save(update_fields=["is_dispensed", "dispensed_at",
                                     "dispensed_by", "updated_at"])
            self.prescription.sync_status()
        return self


class _PrescriberDue(TenantOwnedModel):
    """Shared shape of money owed to a prescriber: pending until it is paid."""

    class Status(models.TextChoices):
        PENDING = "pending"
        PAID = "paid"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def mark_paid(self):
        if self.status == self.Status.PAID:
            raise ValueError("That has already been paid.")
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])
        return self


class PrescriberCommission(_PrescriberDue):
    """A share of one sale, earned by whoever wrote the script.

    Every figure is a snapshot: repricing the drugs or changing the
    prescriber's rate tomorrow must not move what was earned today.
    """

    prescriber = models.ForeignKey(
        Prescriber, on_delete=models.CASCADE, related_name="commissions"
    )
    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="commissions"
    )
    sale = models.ForeignKey(
        "pos.Sale", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriber_commissions",
    )
    patient_name = models.CharField(max_length=200, blank=True)
    sales_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2,
                                            default=0)

    class Meta:
        ordering = ("-created_at", "-id")
        # One commission per sale on a script, so re-dispensing cannot pay twice.
        unique_together = ("prescription", "sale")
        indexes = [
            models.Index(fields=["tenant", "prescriber", "status"]),
            models.Index(fields=["tenant", "prescription"]),
        ]

    def __str__(self):
        return (f"Commission {self.pk} — {self.prescriber_id} "
                f"({self.commission_rate}%)")


class ConsultationPayout(_PrescriberDue):
    """The flat consultation fee charged at the till and owed to the writer.

    One per script, however many times it is part-filled: the patient was
    consulted once.
    """

    prescriber = models.ForeignKey(
        Prescriber, on_delete=models.CASCADE, related_name="consultation_payouts"
    )
    prescription = models.OneToOneField(
        Prescription, on_delete=models.CASCADE, related_name="consultation_payout"
    )
    patient_name = models.CharField(max_length=200, blank=True)
    consultation_category = models.CharField(max_length=1, blank=True)
    consultation_fee = models.DecimalField(max_digits=12, decimal_places=2,
                                           default=0)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "prescriber", "status"])]

    def __str__(self):
        return f"Consultation payout {self.pk} — {self.consultation_fee}"
