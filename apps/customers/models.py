"""Customers: who the pharmacy sells to, and the money they hold with it.

A ``Customer`` is the counter's record of a buyer — retail or wholesale, with
a phone number that identifies them on a repeat visit. It is deliberately not
``patients.Patient``: a patient is a clinical record with a hospital number,
while most people who buy paracetamol are neither registered nor examined.
Where the two are the same person, ``patient`` links them.

The wallet is prepaid money the pharmacy already holds. Top-ups add to it,
purchases draw it down, and a purchase that overdraws it records the shortfall
as debt rather than refusing the sale — the goods have left the shelf either
way, so the ledger must say so.
"""
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.tenants.models import TenantOwnedModel

MONEY = Decimal("0.01")


def _money(value):
    return Decimal(value).quantize(MONEY)


class Customer(TenantOwnedModel):
    """A buyer the pharmacy knows by name and number."""

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    is_wholesale = models.BooleanField(default=False)
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    outstanding_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    join_date = models.DateField(default=timezone.localdate)
    last_visit = models.DateField(null=True, blank=True)
    # The clinical record for this person, when there is one. Insurance is read
    # from there too: ponytail: cover is modelled once, in
    # ``pharmacy.HmoEnrollment``, not copied onto the counter record where it
    # would go stale the first time a card is renewed.
    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="pharmacy_customers",
    )
    prescriber = models.ForeignKey(
        "prescriptions.Prescriber", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="patients",
    )
    blood_group = models.CharField(max_length=5, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    allergies = models.JSONField(default=list, blank=True)
    chronic_conditions = models.JSONField(default=list, blank=True)
    current_medications = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "id")
        unique_together = ("tenant", "phone")
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "is_wholesale"]),
        ]

    def __str__(self):
        return self.name

    @property
    def total_purchases(self):
        """What this customer has ever spent, cancelled sales excluded."""
        total = self.sales.exclude(status="cancelled").aggregate(
            t=models.Sum("total")
        )["t"]
        return _money(total or 0)

    # --- wallet ----------------------------------------------------------
    def _wallet_row(self, txn_type, amount, *, method="", note=""):
        return WalletTransaction.all_objects.create(
            tenant=self.tenant, customer=self, txn_type=txn_type,
            method=method, amount=_money(amount), note=note,
        )

    def top_up(self, amount, *, method="cash", note=""):
        """Take money onto the wallet. Debt is cleared before credit is added.

        Someone paying in while they owe is paying the debt off first — that is
        what they think they are doing, and leaving the debt standing next to a
        positive balance would misstate both.
        """
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("A top-up must be positive.")
        with transaction.atomic():
            row = self._wallet_row("topup", amount, method=method, note=note)
            settled = min(self.outstanding_debt, amount)
            self.outstanding_debt = _money(self.outstanding_debt - settled)
            self.wallet_balance = _money(self.wallet_balance + amount - settled)
            self.save(update_fields=["wallet_balance", "outstanding_debt",
                                     "updated_at"])
        return row

    def deduct(self, amount, *, note=""):
        """Take money off the wallet outright — a correction, not a purchase."""
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("A deduction must be positive.")
        if amount > self.wallet_balance:
            raise ValueError("That is more than the wallet holds.")
        with transaction.atomic():
            row = self._wallet_row("deduct", amount, note=note)
            self.wallet_balance = _money(self.wallet_balance - amount)
            self.save(update_fields=["wallet_balance", "updated_at"])
        return row

    def charge(self, amount, *, note=""):
        """Spend the wallet on a sale. Returns (paid, credit, transaction).

        The wallet pays what it can; the rest becomes debt. The caller decides
        what that means for the sale — see ``pos.Sale.Status.CREDIT``.
        """
        amount = _money(amount)
        if amount <= 0:
            raise ValueError("A charge must be positive.")
        with transaction.atomic():
            paid = min(self.wallet_balance, amount)
            credit = _money(amount - paid)
            row = self._wallet_row("purchase", amount, note=note)
            self.wallet_balance = _money(self.wallet_balance - paid)
            self.outstanding_debt = _money(self.outstanding_debt + credit)
            self.last_visit = timezone.localdate()
            self.save(update_fields=["wallet_balance", "outstanding_debt",
                                     "last_visit", "updated_at"])
        return paid, credit, row

    def refund(self, amount, *, note=""):
        """Put a refund back onto the wallet."""
        return self.top_up(amount, method="", note=note or "Refund")


class WalletTransaction(TenantOwnedModel):
    """Append-only: every movement of a customer's prepaid money.

    ``method`` is how a top-up's cash actually arrived, which is what the sales
    report needs to attribute real money received to cash, POS or transfer. It
    is blank on the other kinds, where no money changed hands at the counter.
    """

    class Kind(models.TextChoices):
        TOPUP = "topup", "Top-up"
        DEDUCT = "deduct", "Deduction"
        PURCHASE = "purchase", "Purchase"

    class Method(models.TextChoices):
        CASH = "cash"
        POS = "pos"
        TRANSFER = "transfer"

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="wallet_transactions"
    )
    txn_type = models.CharField(max_length=20, choices=Kind.choices)
    method = models.CharField(max_length=20, choices=Method.choices, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "customer", "txn_type"])]

    def __str__(self):
        return f"{self.txn_type} {self.amount} ({self.customer_id})"
