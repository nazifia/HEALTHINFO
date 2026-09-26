"""Prescriptions the pharmacy dispenses against.

This is the counter's prescription: who it is for, a list of drugs, and a
line-by-line record of what has actually been handed over. It is not
``analytics.Prescription``, which is a de-identified clinical record for
surveillance — the two answer different questions and neither should be made
to answer the other's.
"""
from difflib import SequenceMatcher

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import normalize_phone
from apps.tenants.models import TenantOwnedModel


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
        PORTAL = "portal"       # sent in from outside the counter

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
    # Whoever signed the paper script, as written on it.
    doctor_name = models.CharField(max_length=200, blank=True)
    diagnosis = models.TextField(blank=True)
    notes = models.TextField(blank=True)
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
        # A script written against a customer or patient record carries their
        # number too: another pharmacy finds and fills it on the number alone
        # (by_number, Sale.patient_number), never on this counter's record ids.
        if not self.customer_phone:
            for who in (self.customer, self.patient):
                if who is not None and who.phone:
                    self.customer_phone = who.phone
                    break
        # One shape for the number, so a script written up as "+234 803 123
        # 4567" is still found by the "08031234567" on the patient's card.
        self.customer_phone = normalize_phone(self.customer_phone)
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

    def fill_from(self, sale):
        """Tick off the lines a sale's items are the drug for.

        The till is where the drug leaves the shelf, so a sale naming the
        script is what marks it filled — at the pharmacy that wrote it up, or
        at any other. A line matches a sold item by stock item, by catalog
        drug, or failing both by name: another pharmacy's shelf never carries
        this one's item ids.
        """
        from apps.analytics.capture import medication_for

        def same_name(a, b):
            # "Paracetemol" at one counter is "Paracetamol" at another.
            # ponytail: difflib ratio, 0.9 keeps cefixime/cefotaxime apart;
            # strip strengths ("500mg") if labels rather than spellings differ.
            return a == b or SequenceMatcher(None, a, b).ratio() >= 0.9

        sold = [(s.item_id, medication_for(sale.tenant_id, s.item, s.name),
                 (s.name or "").strip().lower())
                for s in sale.lines.select_related("item")]
        for line in self._lines().filter(is_dispensed=False).select_related("item"):
            drug = medication_for(self.tenant_id, line.item, line.name)
            if any(line.item_id == item_id
                   or (drug is not None and drug == med)
                   or same_name(line.name.strip().lower(), name)
                   for item_id, med, name in sold):
                line.mark_dispensed(user=sale.served_by)
        return self


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
