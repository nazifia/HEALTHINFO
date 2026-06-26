"""Build searchable text for content objects and upsert their embeddings."""
from django.contrib.contenttypes.models import ContentType

from .embeddings import embed
from .models import ContentEmbedding


def _text_for(obj) -> str:
    """Flatten an object's meaningful fields into one blob for embedding."""
    cls = obj.__class__.__name__
    if cls == "Disease":
        parts = [obj.name, obj.description, obj.causes, obj.treatment, obj.prevention]
    elif cls == "Medication":
        parts = [obj.generic_name, obj.brand_name, obj.description, obj.indications]
    elif cls == "Symptom":
        parts = [obj.name, obj.description]
    else:
        parts = [str(obj)]
    return "\n".join(p for p in parts if p)


def index_object(obj) -> ContentEmbedding:
    text = _text_for(obj)
    ct = ContentType.objects.get_for_model(obj)
    row, _ = ContentEmbedding.all_objects.update_or_create(
        tenant=obj.tenant,
        content_type=ct,
        object_id=obj.pk,
        defaults={"text": text, "embedding": embed(text)},
    )
    return row
