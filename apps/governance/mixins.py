from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role

from .models import AuditLog
from .serializers import AuditLogSerializer, TransitionSerializer
from .workflow import perform_transition


class WorkflowViewSetMixin:
    """Adds /transition/ and /history/ actions + hides unpublished from public.

    Drop onto any ModelViewSet whose model has a ``status`` field.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Public users only ever see published content; staff see all statuses.
        if user.is_authenticated and user.role == Role.PUBLIC:
            return qs.filter(status="published")
        return qs

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        obj = self.get_object()
        s = TransitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            perform_transition(
                obj, request.user, s.validated_data["to"], s.validated_data["note"]
            )
        except ValidationError as e:
            return Response({"detail": e.messages[0]}, status=http.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=http.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        obj = self.get_object()
        logs = AuditLog.objects.filter(
            content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
        )
        return Response(AuditLogSerializer(logs, many=True).data)
