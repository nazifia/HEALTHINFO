"""Branches: the physical sites one pharmacy (tenant) trades from.

A tenant is the business; a branch is a shop. Stock, sales, shifts and
prescriptions carry the branch they happened at, so a two-shop pharmacy can
count one drawer without counting the other's.

There is no cap on how many branches a tenant may open — the count is an
operational fact, not something sold.
"""
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tenants.current import get_current_tenant
from apps.tenants.models import Tenant, TenantOwnedModel


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


def ensure_pharmacy(tenant):
    """Give a tenant the site it dispenses from. Idempotent.

    Every facility dispenses from somewhere: a pharmacy trades from its own
    shop, a hospital from the pharmacy inside it. Both are the tenant's main
    branch — stock, sales and shifts hang off a branch, so a hospital without
    one has nowhere to put a drug or take a payment.

    Returns the branch, existing or new. Safe to call again on a tenant that
    already has one.
    """
    existing = Branch.all_objects.filter(tenant=tenant, is_main=True).first()
    if existing:
        return existing
    name = tenant.name
    if tenant.kind == Tenant.Kind.HOSPITAL:
        name = f"{tenant.name} Pharmacy"[:200]  # Branch.name is max_length=200
    branch, _ = Branch.all_objects.get_or_create(
        tenant=tenant, name=name,
        defaults={"address": tenant.address, "is_main": True},
    )
    return branch


@receiver(post_save, sender=Tenant, dispatch_uid="branches.ensure_pharmacy")
def _new_tenant_gets_a_pharmacy(sender, instance, created, **kwargs):
    """Every tenant leaves creation with a pharmacy, whichever path made it.

    On the signal rather than in the signup serializer because tenants are also
    created from the admin, the super-admin API and the seed commands, and each
    of those needs the branch just as much.
    """
    if created:
        ensure_pharmacy(instance)
