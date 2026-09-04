"""Customers API: who buys, and the prepaid money they hold with the pharmacy.

The wallet is never PATCHed. It moves through ``top-up``, ``deduct`` and the
sale that spends it, each of which writes a ``WalletTransaction`` — so the
balance is always explained by a row somebody can point at.
"""
from decimal import Decimal

from django.db.models import Count, Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsPharmacyStaff,
    IsTenantMember,
    is_pharmacy_admin,
)
from apps.inventory.views import PharmacyViewSet, body
from config.responses import success

from .models import Customer, WalletTransaction
from .serializers import (
    CustomerSerializer,
    WalletInputSerializer,
    WalletTransactionSerializer,
)

ZERO = Decimal("0.00")


class CustomerViewSet(PharmacyViewSet):
    """The counter's customer list, and their wallets."""

    model = Customer
    serializer_class = CustomerSerializer
    filterset_fields = ("is_wholesale", "is_active", "patient", "prescriber")
    search_fields = ("name", "phone", "email")
    ordering_fields = ("name", "created_at", "wallet_balance", "outstanding_debt")

    def get_queryset(self):
        return Customer.objects.select_related("patient", "prescriber")

    def _wallet_action(self, request, call, message):
        customer = self.get_object()
        data = body(WalletInputSerializer, request)
        try:
            call(customer, data)
        except ValueError as exc:
            raise ValidationError({"amount": str(exc)}) from exc
        customer.refresh_from_db()
        return success(f"{message} Balance: {customer.wallet_balance}.",
                       CustomerSerializer(customer).data)

    @action(detail=True, methods=["post"], url_path="top-up")
    def top_up(self, request, pk=None):
        """Take money onto the wallet. Any debt is settled out of it first."""
        return self._wallet_action(
            request,
            lambda c, d: c.top_up(d["amount"], method=d["method"],
                                  note=d.get("note", "")),
            "Wallet topped up.",
        )

    @action(detail=True, methods=["post"], url_path="deduct")
    def deduct(self, request, pk=None):
        """Take money off the wallet outright. Admin only — this is a
        correction, and a correction that moves money needs an owner."""
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can deduct from a wallet.")
        return self._wallet_action(
            request,
            lambda c, d: c.deduct(d["amount"], note=d.get("note", "")),
            "Wallet debited.",
        )

    @action(detail=True, methods=["get"], url_path="wallet")
    def wallet(self, request, pk=None):
        """The wallet's balance and the rows that explain it."""
        customer = self.get_object()
        rows = WalletTransaction.objects.filter(customer=customer)
        return Response({
            "balance": customer.wallet_balance,
            "outstanding_debt": customer.outstanding_debt,
            "transactions": WalletTransactionSerializer(rows, many=True).data,
        })

    @action(detail=False, methods=["get"], url_path="debtors")
    def debtors(self, request):
        """Who owes the pharmacy money, largest first."""
        qs = self.get_queryset().filter(outstanding_debt__gt=0).order_by(
            "-outstanding_debt"
        )
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """How many customers there are, and what the wallets hold between them."""
        qs = self.get_queryset()
        totals = qs.aggregate(
            total=Count("id"), wallets=Sum("wallet_balance"),
            debt=Sum("outstanding_debt"),
        )
        return Response({
            "total": totals["total"] or 0,
            "retail": qs.filter(is_wholesale=False).count(),
            "wholesale": qs.filter(is_wholesale=True).count(),
            "wallet_balance": totals["wallets"] or ZERO,
            "outstanding_debt": totals["debt"] or ZERO,
        })


class WalletTransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """The wallet ledger. Read-only: rows are written by the actions above."""

    serializer_class = WalletTransactionSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("customer", "txn_type", "method")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return WalletTransaction.objects.select_related("customer")
