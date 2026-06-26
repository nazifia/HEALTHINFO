from celery import shared_task
from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType


@shared_task
def embed_object(app_label, model, pk):
    Model = django_apps.get_model(app_label, model)
    obj = Model.all_objects.filter(pk=pk).first()
    if obj is None:
        return
    from .indexing import index_object  # local import: avoid app-load cycle

    index_object(obj)


@shared_task
def remove_embedding(app_label, model, pk):
    from .models import ContentEmbedding

    Model = django_apps.get_model(app_label, model)
    ct = ContentType.objects.get_for_model(Model)
    ContentEmbedding.all_objects.filter(content_type=ct, object_id=pk).delete()


@shared_task
def reindex_all():
    from django.core.management import call_command

    call_command("reindex")
