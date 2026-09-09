"""Which jurisdiction a request reads through.

A health authority seat answers for the patch on its own user row. A platform
admin carries none, which is the whole country — until they pick one, which
arrives as an ``X-Jurisdiction-ID`` header (or a ``?jurisdiction=`` param) and
narrows every cross-tenant rollup, the facility list and the user list to that
state and everything under it.

Picking only ever narrows. A seat may drill into a local government inside its
own patch; a pick outside that patch is ignored rather than obeyed, so the
header can't be used to read sideways into another authority's state.
"""
from .models import Jurisdiction


def selected_jurisdiction(request):
    """The seat's jurisdiction, narrowed by the picked one. None = national."""
    seat = getattr(request.user, "jurisdiction", None)
    raw = (request.headers.get("X-Jurisdiction-ID")
           or request.GET.get("jurisdiction") or "").strip()
    if not raw.isdigit():
        return seat
    picked = Jurisdiction.objects.filter(pk=raw).first()
    if picked is None:
        return seat
    if seat is not None and not seat.subtree().filter(pk=picked.pk).exists():
        return seat
    return picked


def scope_to_selection(qs, request, field="tenant__jurisdiction"):
    """Narrow a cross-tenant queryset to the picked jurisdiction's subtree."""
    picked = selected_jurisdiction(request)
    if picked is None:
        return qs
    return qs.filter(**{f"{field}__in": picked.subtree()})
