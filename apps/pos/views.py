"""Point-of-sale API.

A sale is a financial record: there is no update and no delete anywhere here.
A mistake is undone by ``cancel`` (the whole basket) or by a ``return`` (one
line), both of which put the stock back and say so on the ledger.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.shortcuts import render
from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsPharmacyAdminOrReadOnly,
    IsPharmacyStaff,
    IsTenantMember,
    is_pharmacy_admin,
)
from apps.inventory.models import OutOfStock
from apps.inventory.serializers import StockBatchSerializer
from apps.inventory.views import PharmacyViewSet, body
from config.responses import success

from .models import (
    Cashier,
    DispensingLog,
    Expense,
    ExpenseCategory,
    Notification,
    PaymentRequest,
    PurchaseOrder,
    ReturnRecord,
    Sale,
    SaleItem,
    TillSession,
    receive_purchase_line,
    record_return,
)
from .serializers import (
    CashierSerializer,
    CompleteRequestSerializer,
    DispensingLogSerializer,
    ExpenseCategorySerializer,
    ExpenseSerializer,
    NotificationSerializer,
    PaymentRequestSerializer,
    PurchaseOrderSerializer,
    ReceivePurchaseSerializer,
    ReturnInputSerializer,
    ReturnRecordSerializer,
    SaleCancelSerializer,
    SalePaymentInputSerializer,
    SaleSerializer,
    TillCloseSerializer,
    TillSessionSerializer,
)

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
ZERO = Decimal("0.00")


def _range(request):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD into date objects (None if absent)."""
    return (
        parse_date(request.query_params.get("from", "") or ""),
        parse_date(request.query_params.get("to", "") or ""),
    )


def _apply_range(qs, start, end):
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs


class CashierViewSet(PharmacyViewSet):
    """Who may take money, and at which counter. Admin keeps the list."""

    model = Cashier
    serializer_class = CashierSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("kind", "is_active", "user")
    search_fields = ("name", "code")

    def get_queryset(self):
        return Cashier.objects.select_related("user")


class SaleViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                  mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Dispensing and taking payment.

    No update and no delete: a sale is a financial record. A mistake is
    reversed with ``cancel``, which puts the stock back and voids the claim,
    or with ``return`` for a single line.
    """

    serializer_class = SaleSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "payment_method", "patient", "customer",
                        "branch", "is_wholesale", "served_by", "cashier")
    search_fields = ("reference", "buyer_name")
    ordering_fields = ("created_at", "total")

    def get_queryset(self):
        return Sale.objects.select_related(
            "patient", "customer", "served_by", "branch"
        ).prefetch_related("lines", "payments")

    def perform_create(self, serializer):
        # One transaction for the basket: a line that can't be filled rolls back
        # the stock the earlier lines already took.
        with transaction.atomic():
            serializer.save(served_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Take money against the patient's side of the bill."""
        sale = self.get_object()
        data = body(SalePaymentInputSerializer, request)
        try:
            sale.record_payment(data["amount"], method=data.get("method"),
                                till=TillSession.open_for(request.user),
                                user=request.user)
        except ValueError as exc:
            raise ValidationError({"amount": str(exc)}) from exc
        message = "Payment recorded."
        if sale.change_due:
            message = f"Payment recorded. Change due: {sale.change_due}."
        return success(message, SaleSerializer(sale).data)

    @action(detail=True, methods=["post"], url_path="pay-wallet")
    def pay_wallet(self, request, pk=None):
        """Settle the bill out of the customer's wallet.

        A wallet short of the bill still dispenses: the shortfall becomes the
        customer's debt and the sale is marked CREDIT, which keeps it out of
        revenue until it is paid.
        """
        sale = self.get_object()
        try:
            sale, credit = sale.pay_from_wallet(user=request.user)
        except ValueError as exc:
            raise ValidationError({"customer": str(exc)}) from exc
        message = ("Paid from wallet." if credit <= 0
                   else f"Wallet short by {credit}; recorded as customer debt.")
        return success(message, SaleSerializer(sale).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Reverse the sale and return every unit to the batch it came from."""
        sale = self.get_object()
        data = body(SaleCancelSerializer, request)
        sale.cancel(reason=data.get("reason", ""), user=request.user)
        return success("Sale cancelled and stock returned.",
                       SaleSerializer(sale).data)

    @action(detail=True, methods=["post"], url_path="return")
    def take_return(self, request, pk=None):
        """Take one line back: stock to its batch, refund out the chosen way."""
        sale = self.get_object()
        data = body(ReturnInputSerializer, request)
        line = data["line"]
        if line.sale_id != sale.pk:
            raise ValidationError({"line": "That line belongs to another sale."})
        try:
            record = record_return(
                line, data["quantity"], refund_method=data["refund_method"],
                reason=data.get("reason", ""), user=request.user,
            )
        except ValueError as exc:
            raise ValidationError({"quantity": str(exc)}) from exc
        sale.refresh_from_db()
        return success(
            f"Returned {data['quantity']} unit(s); {record.amount} refunded.",
            {"return": ReturnRecordSerializer(record).data,
             "sale": SaleSerializer(sale).data},
            status=201,
        )

    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, pk=None):
        """A printable receipt for the sale.

        Server-rendered HTML sized for an 80mm till roll and for A4 alike — the
        browser's own print dialog is the printer driver, so there is no PDF
        library and no print server to keep alive.
        """
        sale = self.get_object()
        return render(request, "pharmacy/receipt.html", {
            "sale": sale,
            "lines": SaleItem.all_objects.filter(sale=sale).select_related(
                "item", "batch"
            ),
            "tenant": request.tenant,
        })

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Takings over ?from/?to: what was billed, collected and still owed."""
        start, end = _range(request)
        qs = _apply_range(self.get_queryset(), start, end).exclude(
            status=Sale.Status.CANCELLED
        )
        totals = qs.aggregate(
            sales=Count("id"), billed=Sum("total"),
            patient_share=Sum("patient_payable"), hmo_share=Sum("hmo_payable"),
            collected=Sum("amount_paid"),
        )
        billed = totals["billed"] or ZERO
        patient_share = totals["patient_share"] or ZERO
        collected = totals["collected"] or ZERO
        lines = _apply_range(SaleItem.objects.exclude(
            sale__status=Sale.Status.CANCELLED
        ), start, end)
        top = (lines.values("item", "item__name")
               .annotate(units=Sum("quantity"),
                         revenue=Sum(ExpressionWrapper(
                             F("quantity") * F("unit_price"),
                             output_field=MONEY_FIELD)))
               .order_by("-units")[:10])
        return Response({
            "sales": totals["sales"] or 0,
            "billed": billed,
            "patient_share": patient_share,
            "hmo_share": totals["hmo_share"] or ZERO,
            "collected": collected,
            "outstanding": max(patient_share - collected, ZERO),
            "top_items": [
                {"item": row["item"], "name": row["item__name"],
                 "units": row["units"], "revenue": row["revenue"]}
                for row in top
            ],
        })


class ReturnRecordViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """What has come back, and what was refunded for it. Read-only: a return
    is taken on the sale it belongs to."""

    serializer_class = ReturnRecordSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("sale", "refund_method", "returned_by")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return ReturnRecord.objects.select_related("sale", "line")


class DispensingLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """Who handed out what, and when. Written by the sale, never by hand."""

    serializer_class = DispensingLogSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("item", "user", "status", "sale")
    search_fields = ("name", "brand")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return DispensingLog.objects.select_related("item", "user", "sale")


class PaymentRequestViewSet(PharmacyViewSet):
    """The dispenser's basket, waiting on a cashier.

    Nothing leaves the shelf until ``complete``: until then this is a list of
    what someone intends to sell, not a sale.
    """

    model = PaymentRequest
    serializer_class = PaymentRequestSerializer
    filterset_fields = ("status", "cashier", "dispenser", "customer", "store")
    search_fields = ("reference", "buyer_name")
    ordering_fields = ("created_at", "total_amount")

    def get_queryset(self):
        return PaymentRequest.objects.select_related(
            "dispenser", "cashier", "customer"
        ).prefetch_related("lines")

    def perform_create(self, serializer):
        serializer.save(dispenser=self.request.user)

    def _transition(self, call, message):
        request_row = self.get_object()
        try:
            result = call(request_row)
        except OutOfStock as exc:
            raise ValidationError({"items": str(exc)}) from exc
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        request_row.refresh_from_db()
        return result, success(message,
                               PaymentRequestSerializer(request_row).data)

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        """A cashier takes the basket. Stock has still not moved."""
        cashier = Cashier.objects.filter(user=request.user, is_active=True).first()
        if cashier is None:
            raise PermissionDenied("You are not set up as a cashier.")
        _result, response = self._transition(lambda r: r.accept(cashier),
                                             "Request accepted.")
        return response

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Refuse the basket, with a reason the dispenser can read."""
        data = body(CompleteRequestSerializer, request)
        _result, response = self._transition(
            lambda r: r.reject(data.get("reason", "")), "Request rejected."
        )
        return response

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """The dispenser withdraws the basket before it is paid for."""
        _result, response = self._transition(lambda r: r.cancel(),
                                             "Request cancelled.")
        return response

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Turn the basket into a sale. This is where stock moves."""
        data = body(CompleteRequestSerializer, request)
        sale, _response = self._transition(
            lambda r: r.complete(user=request.user,
                                 payment_method=data["payment_method"]),
            "Request completed.",
        )
        return success("Sale created from the request.",
                       SaleSerializer(sale).data, status=201)


class TillSessionViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                         mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The cash drawer: opened with a float, closed with a count.

    No update and no delete - a counted drawer is a financial record. Cash
    payments book themselves into the cashier's open drawer as they are taken.
    """

    serializer_class = TillSessionSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "opened_by", "branch")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return TillSession.objects.select_related("opened_by").prefetch_related(
            "payments"
        )

    def perform_create(self, serializer):
        if TillSession.open_for(self.request.user):
            raise ValidationError(
                "You already have a drawer open; close it before opening another."
            )
        serializer.save(opened_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        """Count the drawer and shut it; the variance comes back in the message."""
        session = self.get_object()
        data = body(TillCloseSerializer, request)
        try:
            session.close(data["amount"], notes=data.get("notes", ""))
        except ValueError as exc:
            raise ValidationError({"amount": str(exc)}) from exc
        return success(f"Drawer closed. Variance: {session.variance}.",
                       TillSessionSerializer(session).data)

    @action(detail=True, methods=["get"], url_path="totals")
    def totals(self, request, pk=None):
        """What went through this drawer, by how the money arrived."""
        return Response(self.get_object().totals)


class ExpenseCategoryViewSet(PharmacyViewSet):
    """What money that isn't stock gets spent on. Admin keeps the list."""

    model = ExpenseCategory
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    search_fields = ("name",)
    ordering_fields = ("name",)


class ExpenseViewSet(PharmacyViewSet):
    """Money out that bought no stock.

    Cash expenses name the drawer they came out of, so the till still counts
    correctly at close.
    """

    model = Expense
    serializer_class = ExpenseSerializer
    filterset_fields = ("category", "payment_source", "branch", "till_session",
                        "date")
    search_fields = ("description",)
    ordering_fields = ("date", "amount", "created_at")

    def get_queryset(self):
        return Expense.objects.select_related("category")

    def perform_create(self, serializer):
        source = serializer.validated_data.get("payment_source",
                                               Expense.Source.CASH)
        till = serializer.validated_data.get("till_session")
        if source == Expense.Source.CASH and till is None:
            till = TillSession.open_for(self.request.user)
        serializer.save(created_by=self.request.user, till_session=till)

    def perform_destroy(self, instance):
        if not is_pharmacy_admin(self.request.user):
            raise PermissionDenied("Only the pharmacy admin can delete an expense.")
        super().perform_destroy(instance)


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """What the app is telling this user. Only the read flag is writable."""

    serializer_class = NotificationSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("kind", "priority", "is_read")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        # Scoped to the caller: a notification is addressed to one person, and
        # listing everyone's would leak who is being chased about what.
        return Notification.objects.filter(user=self.request.user).select_related(
            "item"
        )

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """Clear the badge: mark everything unread as read."""
        n = self.get_queryset().filter(is_read=False).update(is_read=True)
        return success(f"{n} notification(s) marked read.", {"updated": n})


class PurchaseOrderViewSet(PharmacyViewSet):
    """Orders placed with suppliers, and the deliveries booked against them."""

    model = PurchaseOrder
    serializer_class = PurchaseOrderSerializer
    filterset_fields = ("status", "supplier", "branch")
    search_fields = ("reference", "notes")
    ordering_fields = ("created_at", "expected_date")

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("supplier").prefetch_related(
            "lines"
        )

    def perform_create(self, serializer):
        serializer.save(ordered_by=self.request.user)

    def _transition(self, call, message):
        order = self.get_object()
        try:
            call(order)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(message, PurchaseOrderSerializer(order).data)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Send the order to the supplier."""
        return self._transition(lambda o: o.submit(), "Order submitted.")

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel what has not been delivered."""
        return self._transition(lambda o: o.cancel(), "Order cancelled.")

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        """Book a delivery against one line: stock in, line counted up.

        The order's status follows the received counts, so a short delivery
        leaves it PARTIAL and the outstanding quantity is still visible.
        """
        order = self.get_object()
        data = body(ReceivePurchaseSerializer, request)
        line = data["line"]
        if line.order_id != order.pk:
            raise ValidationError({"line": "That line belongs to another order."})
        try:
            batch = receive_purchase_line(
                line, data["quantity"], batch_number=data["batch_number"],
                expiry_date=data.get("expiry_date"),
                unit_cost=data.get("unit_cost"), user=request.user,
            )
        except ValueError as exc:
            raise ValidationError({"quantity": str(exc)}) from exc
        order.refresh_from_db()
        return success(
            f"Received {data['quantity']} unit(s) of {line.item.name}.",
            {"batch": StockBatchSerializer(batch).data,
             "order": PurchaseOrderSerializer(order).data},
            status=201,
        )
