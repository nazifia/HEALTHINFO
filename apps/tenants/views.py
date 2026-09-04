from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsSuperAdmin
from apps.governance.models import AuditLog
from apps.governance.serializers import AuditLogSerializer
from config.responses import success

from .models import Tenant
from .serializers import TenantSerializer


# to_status of the audit row a super-admin writes when they enter a tenant.
# from_status stays blank: entering an organization is not a state change on
# it, it is a visit to it.
OPENED = "opened"


class TenantViewSet(viewsets.ModelViewSet):
    """Platform-wide tenant administration (super-admin only).

    Bypasses tenant scoping — Tenant isn't a TenantOwnedModel, so its default
    manager already sees every row. Adds a user_count and subscription
    approve/reject/suspend actions for the super-admin dashboard.
    """

    serializer_class = TenantSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ("subscription_status", "status", "kind")

    def get_queryset(self):
        return Tenant.objects.annotate(user_count=Count("users")).order_by("name")

    def _by_kind(self, request, kind):
        """Kind-scoped list. Same shape as /tenants/ so paging and filters hold."""
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()).filter(kind=kind))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=False, methods=["get"])
    def hospitals(self, request):
        return self._by_kind(request, Tenant.Kind.HOSPITAL)

    @action(detail=False, methods=["get"])
    def pharmacies(self, request):
        return self._by_kind(request, Tenant.Kind.PHARMACY)

    def _set_subscription(self, request, pk, value):
        tenant = self.get_object()
        tenant.subscription_status = value
        tenant.save(update_fields=["subscription_status", "updated_at"])
        return success(
            f"Subscription {value}.",
            TenantSerializer(tenant).data,
        )

    @action(detail=True, methods=["post"], url_path="open")
    def open_as(self, request, pk=None):
        """Record that this super-admin is about to work inside this tenant.

        Scoping itself is the X-Tenant-ID header the client then sends, so this
        endpoint exists only for the trail: a super-admin reaches every
        organization, and who entered which one must be answerable afterwards.
        """
        tenant = self.get_object()
        AuditLog.objects.create(
            tenant=tenant,
            user=request.user,
            content_type=ContentType.objects.get_for_model(Tenant),
            object_id=tenant.pk,
            from_status="",
            to_status=OPENED,
        )
        return success(f"Working in {tenant.name}.", TenantSerializer(tenant).data)

    @action(detail=True, methods=["get"], url_path="access-log")
    def access_log(self, request, pk=None):
        """Who opened this organization, and when. Newest first."""
        tenant = self.get_object()
        # all_objects: the reader is a super-admin whose own request carries no
        # tenant, so the scoped manager would answer with nothing.
        logs = AuditLog.all_objects.filter(
            tenant=tenant,
            content_type=ContentType.objects.get_for_model(Tenant),
            object_id=tenant.pk,
            to_status=OPENED,
        ).order_by("-created_at", "-id")
        return Response(AuditLogSerializer(logs, many=True).data)

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
