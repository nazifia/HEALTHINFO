"""Fire-and-forget event recording. Never let analytics break a user request."""
from .tasks import record_event


def track(request, event_type, **fields):
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return
    user_id = request.user.id if request.user.is_authenticated else None
    try:
        record_event.delay(tenant.id, user_id, event_type, **fields)
    except Exception:  # broker down etc. — analytics is best-effort
        pass


def log_ai_interaction(request, question, answer, sources, model_name=""):
    """Persist a RAG Q&A and return its id so the client can attach feedback.

    Synchronous (one INSERT) because the caller needs the id back — celery can't
    return it. Best-effort: a DB hiccup returns None, never 500s the answer.
    ponytail: sync insert is fine; move to async only if write volume hurts.
    """
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return None
    user_id = request.user.id if request.user.is_authenticated else None
    try:
        from .models import AiInteraction

        obj = AiInteraction.all_objects.create(
            tenant_id=tenant.id, user_id=user_id, question=question,
            answer=answer, sources=sources, model_name=model_name,
        )
        return obj.id
    except Exception:
        return None


class ViewTrackingMixin:
    """Records a 'view' event on retrieve. Set ``analytics_object_type``."""

    analytics_object_type = None

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        track(
            request,
            "view",
            object_type=self.analytics_object_type or self.basename,
            object_id=int(kwargs["pk"]),
        )
        return response
