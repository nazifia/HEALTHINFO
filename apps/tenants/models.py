from django.db import models
from django.db.models import Q

from .current import get_current_tenant


class Jurisdiction(models.Model):
    """Geographic tier a tenant reports through: local gov → state → national.

    Self-referential tree, not three tables — a row's `level` says which tier it
    is and `parent` points one tier up. Central collation rolls tenant data up
    this chain (every report carries its tenant, tenant carries its jurisdiction).
    """

    class Level(models.TextChoices):
        LOCAL = "local"        # LGA / county / district
        STATE = "state"
        NATIONAL = "national"  # central

    name = models.CharField(max_length=200)
    level = models.CharField(max_length=20, choices=Level.choices)
    # PROTECT: don't let deleting a state silently orphan its locals.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="children",
    )

    class Meta:
        indexes = [models.Index(fields=["level"])]
        unique_together = ("name", "level", "parent")

    def __str__(self):
        return f"{self.name} ({self.level})"

    def ancestor(self, level):
        """Nearest self-or-ancestor at `level`, or None. Walks parent chain.

        ponytail: linear walk, tree is 3 deep. Cache only if it ever shows in a
        hot loop — it won't at this depth.
        """
        node = self
        while node is not None and node.level != level:
            node = node.parent
        return node


class Tenant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    address = models.TextField(blank=True)
    contact = models.CharField(max_length=120, blank=True)
    logo = models.URLField(blank=True)
    domain = models.CharField(max_length=255, blank=True, db_index=True)
    # Where this tenant sits in the gov hierarchy (usually a local gov). Central
    # rollup folds up from here. Nullable so existing tenants migrate clean.
    jurisdiction = models.ForeignKey(
        Jurisdiction, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tenants",
    )
    subscription_plan = models.CharField(max_length=50, default="free")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class TenantManager(models.Manager):
    """Auto-scopes every query to the current tenant.

    Isolation lives here: any model using this manager only ever sees rows for
    the request's tenant. Use ``all_tenants()`` to bypass (super-admin only).
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is None:
            # No tenant bound (e.g. super-admin context): return nothing by
            # default so a missing middleware never leaks cross-tenant data.
            return qs.none()
        return qs.filter(tenant=tenant)

    def all_tenants(self):
        return super().get_queryset()


class SharedTenantManager(TenantManager):
    """Tenant's own rows PLUS global (tenant IS NULL) shared reference rows.

    Global rows are seeded with no tenant and are readable by every tenant —
    the shared standard catalog. Each tenant can still author its own private
    rows on top. Writes to global rows are gated in the API layer (super-admin
    only); the manager only governs reads.
    """

    def get_queryset(self):
        qs = models.Manager.get_queryset(self)  # skip TenantManager's hard filter
        tenant = get_current_tenant()
        if tenant is None:
            # No tenant bound: expose shared rows only, never private ones.
            return qs.filter(tenant__isnull=True)
        return qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))


class TenantOwnedModel(models.Model):
    # Nullable so a row can be global (shared across all tenants). Private rows
    # still carry their owning tenant; see SharedTenantManager.
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.tenant_id is None:
            tenant = get_current_tenant()
            if tenant is not None:
                self.tenant = tenant
        super().save(*args, **kwargs)


class SharedCatalogModel(TenantOwnedModel):
    """TenantOwnedModel whose rows may be global reference data (tenant=NULL)."""

    objects = SharedTenantManager()

    class Meta:
        abstract = True
