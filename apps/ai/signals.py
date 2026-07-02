"""Keep embeddings in sync with content. Enqueued on commit so the worker only
ever sees rows that actually landed; under test rollback these never fire."""
import sys
from django.db import transaction
from django.db.models.signals import post_delete, post_save

from apps.catalog.models import Disease, Medication, Symptom

from .tasks import embed_object, remove_embedding

# Models gated by the publish workflow: only published content gets indexed.
WORKFLOW = {Disease, Medication}


def _enqueue(instance, *, deleted):
    # Don't queue Celery tasks while loading fixtures
    if "loaddata" in sys.argv:
        return

    label = instance._meta.app_label
    model = instance._meta.model_name
    pk = instance.pk

    if deleted or (type(instance) in WORKFLOW and instance.status != "published"):
        transaction.on_commit(lambda: remove_embedding.delay(label, model, pk))
    else:
        transaction.on_commit(lambda: embed_object.delay(label, model, pk))




def _on_save(sender, instance, **kwargs):
    _enqueue(instance, deleted=False)


def _on_delete(sender, instance, **kwargs):
    _enqueue(instance, deleted=True)


def connect():
    for model in (Disease, Medication, Symptom):
        post_save.connect(_on_save, sender=model, dispatch_uid=f"emb_save_{model.__name__}")
        post_delete.connect(_on_delete, sender=model, dispatch_uid=f"emb_del_{model.__name__}")
