from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.tenants.models import TenantOwnedModel


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
