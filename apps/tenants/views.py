from django.db.models import Count
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsSuperAdmin
from config.responses import success

from .models import Tenant
from .serializers import TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
    """Platform-wide tenant administration (super-admin only).

    Bypasses tenant scoping — Tenant isn't a TenantOwnedModel, so its default
    manager already sees every row. Adds a user_count and subscription
    approve/reject/suspend actions for the super-admin dashboard.
    """

    serializer_class = TenantSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ("subscription_status", "status")

    def get_queryset(self):
        return Tenant.objects.annotate(user_count=Count("users")).order_by("name")

    def _set_subscription(self, request, pk, value):
        tenant = self.get_object()
        tenant.subscription_status = value
        tenant.save(update_fields=["subscription_status", "updated_at"])
        return success(
            f"Subscription {value}.",
            TenantSerializer(tenant).data,
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._set_subscription(request, pk, Tenant.SubscriptionStatus.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._set_subscription(request, pk, Tenant.SubscriptionStatus.REJECTED)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        tenant = self.get_object()
        tenant.status = (
            Tenant.Status.ACTIVE
            if tenant.status == Tenant.Status.SUSPENDED
            else Tenant.Status.SUSPENDED
        )
        tenant.save(update_fields=["status", "updated_at"])
        return success(f"Tenant {tenant.status}.", TenantSerializer(tenant).data)
