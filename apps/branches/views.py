"""Branches API: the sites one pharmacy trades from.

Staff read the list — a dispenser needs to know which shop they are in — but
opening and closing one is the admin's, because every branch is somewhere
stock and cash can go.
"""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsPharmacyAdminOrReadOnly,
    IsPharmacyStaff,
    IsTenantAdminOrReadOnly,
    IsTenantMember,
)
from apps.inventory.views import PharmacyViewSet

from .models import Branch, Shift
from .serializers import BranchSerializer, ShiftSerializer


class BranchViewSet(PharmacyViewSet):
    """One tenant's trading sites."""

    model = Branch
    serializer_class = BranchSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active", "is_main")
    search_fields = ("name", "address", "phone")
    ordering_fields = ("name", "created_at")


class ShiftViewSet(viewsets.ModelViewSet):
    """The roster: who is rostered where, and who is on right now.

    Any tenant member reads it — a nurse needs to know who else is on — but
    only the tenant admin sets it.
    """

    serializer_class = ShiftSerializer
    permission_classes = [IsTenantMember, IsTenantAdminOrReadOnly]
    # Dict form so a calendar can ask for one window: ?starts_at__gte=&
    # starts_at__lt=. A shift that starts before the window and runs into it
    # is outside it — the roster reads by when someone comes on.
    filterset_fields = {
        "branch": ["exact"],
        "user": ["exact"],
        "starts_at": ["gte", "lt"],
    }
    ordering_fields = ("starts_at", "ends_at", "created_at")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        return Shift.objects.all()

    @action(detail=False, methods=["get"])
    def on_duty(self, request):
        """Who is on right now — ?branch=<id> narrows it to one site."""
        branch = request.query_params.get("branch") or None
        shifts = Shift.on_duty(branch=branch)
        return Response({
            "count": shifts.values("user").distinct().count(),
            "results": self.get_serializer(shifts, many=True).data,
        })
