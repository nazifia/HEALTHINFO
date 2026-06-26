"""Content lifecycle state machine: Author -> Reviewer -> Medical Editor -> Publish.

Single source of truth for which transitions exist and who may perform them.
Any model with a ``status`` field (see catalog.Status) plugs in via the service.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role

from .models import AuditLog

# Allowed status edges (forward = progress, backward = reject/recall).
TRANSITIONS = {
    "draft": {"review"},
    "review": {"approved", "draft"},      # approve, or reject to author
    "approved": {"published", "review"},  # publish, or send back to review
    "published": {"archived"},
    "archived": {"draft"},                # revive
}

_AUTHOR = {Role.DOCTOR, Role.PHARMACIST, Role.NURSE, Role.TENANT_ADMIN, Role.SUPER_ADMIN}
_REVIEWER = {Role.DOCTOR, Role.PHARMACIST, Role.TENANT_ADMIN, Role.SUPER_ADMIN}
_EDITOR = {Role.TENANT_ADMIN, Role.SUPER_ADMIN}

# Role required to MOVE INTO a given status.
ROLE_FOR_TARGET = {
    "review": _AUTHOR,
    "draft": _REVIEWER,       # rejecting/recalling back to draft
    "approved": _REVIEWER,
    "published": _EDITOR,
    "archived": _EDITOR,
}


def perform_transition(obj, user, to_status, note=""):
    """Validate + apply a workflow transition and write an audit log.

    Raises ValidationError (bad edge) or PermissionDenied (wrong role).
    """
    current = obj.status
    if to_status not in TRANSITIONS.get(current, set()):
        raise ValidationError(f"Cannot move from '{current}' to '{to_status}'.")
    if user.role not in ROLE_FOR_TARGET.get(to_status, set()):
        raise PermissionDenied(f"Role '{user.role}' cannot set status '{to_status}'.")

    obj.status = to_status
    obj.save(update_fields=["status", "updated_at"])
    AuditLog.objects.create(
        user=user,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        from_status=current,
        to_status=to_status,
        note=note,
    )
    return obj
