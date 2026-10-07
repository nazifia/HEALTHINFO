"""The insurer: an HMO, or NHIA itself.

Cover, enrollments and claims against it live in ``apps.pharmacy``.
"""
from decimal import Decimal

from django.db import models

from apps.tenants.models import TenantOwnedModel


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
    # Some insurers want each claim as the sale happens; others wait for the
    # pharmacy to send it. Off by default, so a claim starts as a draft.
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
        db_table = "pharmacy_hmo"  # moved from apps.pharmacy; table kept

    def __str__(self):
        return self.name
