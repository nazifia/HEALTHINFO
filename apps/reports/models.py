"""What a staff member earns on what they sell.

The reports themselves hold no state — they are queries over ``pos`` and
``inventory``. The one thing they need stored is the rate each person is paid
at, which is a policy the pharmacy sets rather than anything derivable.
"""
from django.db import models

from apps.tenants.models import TenantOwnedModel


class CommissionConfig(TenantOwnedModel):
    """One staff member's commission terms.

    ``rate`` is a percentage of what they sold; ``fixed_bonus`` is added on top
    of it once per period. A row that is switched off stops earning without
    losing what the rate used to be.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="commission_configs"
    )
    rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Percent (0-100) of sales value earned as commission.",
    )
    fixed_bonus = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("user_id",)
        unique_together = ("tenant", "user")

    def __str__(self):
        return f"{self.user_id} — {self.rate}%"
