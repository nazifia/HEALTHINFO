from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models

from apps.tenants.models import TenantOwnedModel

_MODE_CACHE_KEY = "governance:runtime_mode"


class RuntimeConfig(models.Model):
    """Single global row toggling runtime behaviour between dev and prod.

    Only per-request behaviour can switch live. DEBUG, DATABASES, ALLOWED_HOSTS
    and INSTALLED_APPS are read once at process start and still need a restart —
    this flag governs what IS read per request (API error verbosity, plus
    anything you gate on ``current_mode()`` / ``is_prod()``).
    """

    class Mode(models.TextChoices):
        DEV = "dev", "Development"
        PROD = "prod", "Production"

    mode = models.CharField(max_length=4, choices=Mode.choices, default=Mode.DEV)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Runtime mode: {self.get_mode_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)
        cache.delete(_MODE_CACHE_KEY)

    def delete(self, *args, **kwargs):  # singleton: never deleted
        pass


def current_mode():
    """Active runtime mode, cached. Falls back to DEBUG before the row exists."""
    mode = cache.get(_MODE_CACHE_KEY)
    if mode is None:
        cfg = RuntimeConfig.objects.first()
        mode = cfg.mode if cfg else (
            RuntimeConfig.Mode.DEV if settings.DEBUG else RuntimeConfig.Mode.PROD
        )
        # ponytail: short TTL so a save in one worker self-heals others under the
        # default per-process LocMemCache. Use a shared cache backend to flip
        # instantly across workers.
        cache.set(_MODE_CACHE_KEY, mode, 30)
    return mode


def is_prod():
    return current_mode() == RuntimeConfig.Mode.PROD


class AuditLog(TenantOwnedModel):
    """Append-only record of every workflow transition. Never updated."""

    user = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    note = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["content_type", "object_id"])]
        # -id breaks ties when several transitions share a created_at
        # (same-request edits collide at DB timestamp resolution).
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.content_type} #{self.object_id}: {self.from_status}->{self.to_status}"
