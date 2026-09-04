"""Branches API: the sites one pharmacy trades from.

Staff read the list — a dispenser needs to know which shop they are in — but
opening and closing one is the admin's, because every branch is somewhere
stock and cash can go.
"""
from apps.accounts.permissions import (
    IsPharmacyAdminOrReadOnly,
    IsPharmacyStaff,
    IsTenantMember,
)
from apps.inventory.views import PharmacyViewSet

from .models import Branch
from .serializers import BranchSerializer


class BranchViewSet(PharmacyViewSet):
    """One tenant's trading sites."""

    model = Branch
    serializer_class = BranchSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active", "is_main")
    search_fields = ("name", "address", "phone")
    ordering_fields = ("name", "created_at")
