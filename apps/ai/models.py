from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.tenants.models import TenantOwnedModel

EMBED_DIM = 1536  # keep in sync with settings.EMBED_DIM and the migration


class ContentEmbedding(TenantOwnedModel):
    """One row per indexed content object. Decoupled from content models so we
    never have to migrate a vector column onto every table."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    text = models.TextField()
    embedding = models.JSONField(default=list)  # list[float], EMBED_DIM long

    class Meta:
        unique_together = ("tenant", "content_type", "object_id")
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"emb({self.content_type} #{self.object_id})"
