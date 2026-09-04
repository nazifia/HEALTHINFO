"""Branches: the physical sites one pharmacy (tenant) trades from.

A tenant is the business; a branch is a shop. Stock, sales, shifts and
prescriptions carry the branch they happened at, so a two-shop pharmacy can
count one drawer without counting the other's.

There is no cap on how many branches a tenant may open — the count is an
operational fact, not something sold.
"""
from django.db import models

from apps.tenants.current import get_current_tenant
from apps.tenants.models import TenantOwnedModel


class Branch(TenantOwnedModel):
    """One trading site. Exactly one branch per tenant is the main one."""

    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive branches are hidden from the app; their data stays.",
    )
    is_main = models.BooleanField(
        default=False, help_text="The head-office branch. One per tenant."
    )

    class Meta:
        verbose_name_plural = "branches"
        ordering = ("-is_main", "name", "id")
        unique_together = ("tenant", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(is_main=True),
                name="one_main_branch_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.name}{' [main]' if self.is_main else ''}"

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            self.tenant = get_current_tenant()
        if self.is_main:
            # Promoting a branch demotes the previous main first, so the unique
            # constraint above is never the thing that reports the conflict.
            others = Branch.all_objects.filter(
                tenant_id=self.tenant_id, is_main=True
            )
            if self.pk:
                others = others.exclude(pk=self.pk)
            others.update(is_main=False)
        super().save(*args, **kwargs)
