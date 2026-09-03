"""Pharmacy API.

Stock only ever moves through a named door: a receipt, a sale, or an
adjustment. There is deliberately no way to PATCH a batch quantity or a sale
total — every figure a client can change is an input to the money, never the
money itself.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.shortcuts import render
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
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
from config.responses import success

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    PurchaseOrder,
    PurchaseOrderLine,
    Sale,
    SaleItem,
    StockBatch,
    StockItem,
    StockMovement,
    Supplier,
    adjust_stock,
    receive_purchase_line,
    receive_stock,
)
from .serializers import (
    AddClaimsSerializer,
    AdjustStockSerializer,
    ClaimBatchSerializer,
    ClaimDecisionSerializer,
    ClaimPaymentSerializer,
    ClaimSerializer,
    HMOSerializer,
    HmoEnrollmentSerializer,
    PurchaseOrderSerializer,
    ReceivePurchaseSerializer,
    ReceiveStockSerializer,
    SaleCancelSerializer,
    SalePaymentSerializer,
    SaleSerializer,
    StockBatchSerializer,
    StockItemSerializer,
    StockMovementSerializer,
    SupplierSerializer,
)

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


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


def _body(serializer_class, request):
    """Validate an action's body and return its data, or raise DRF's 400."""
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class _PharmacyViewSet(viewsets.ModelViewSet):
    """Tenant-scoped, pharmacy-staff-only base.

    ``model`` supplies the per-request queryset: the manager is re-run every
    time so tenant scoping is never frozen onto the class.
    """

    model = None
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return self.model.objects.all()


class StockItemViewSet(_PharmacyViewSet):
    """The pharmacy's item list — what it sells and what it charges.

    Staff read and dispense against it; only the pharmacy admin edits a price,
    a reorder level or the list itself.
    """

    model = StockItem
    serializer_class = StockItemSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("form", "is_active", "prescription_only", "medication")
    search_fields = ("name", "sku")
    ordering_fields = ("name", "unit_price", "created_at")

    def get_queryset(self):
        # One annotated total per item — the alternative is an aggregate query
        # per row when the list serializes. Coalesced to 0 so an item that has
        # never been stocked still sorts and filters as empty rather than NULL;
        # that item is exactly the one the low-stock list must not drop.
        # Ordering is restated because the aggregate annotation drops the
        # model's default ordering, and an unordered list paginates inconsistently.
        return StockItem.objects.annotate(
            stock_on_hand=Coalesce(Sum("batches__quantity"), 0)
        ).order_by("name", "id")

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        """Book in a consignment: creates or tops up its batch, logs the receipt."""
        item = self.get_object()
        data = _body(ReceiveStockSerializer, request)
        batch = receive_stock(
            item, data["quantity"], batch_number=data["batch_number"],
            expiry_date=data.get("expiry_date"), cost_price=data.get("cost_price"),
            supplier=data.get("supplier", ""), user=request.user,
        )
        return success(
            f"Received {data['quantity']} {item.unit}(s) of {item.name}.",
            StockBatchSerializer(batch).data,
            status=201,
        )

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        """Items at or below their reorder level — the buying list."""
        qs = self.get_queryset().filter(
            is_active=True, stock_on_hand__lte=F("reorder_level")
        )
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="valuation")
    def valuation(self, request):
        """What the shelf is worth: cost (what it tied up) and retail (what it
        would fetch), from live batch quantities."""
        batches = StockBatch.objects.filter(quantity__gt=0)
        cost = batches.aggregate(
            v=Sum(ExpressionWrapper(F("quantity") * F("cost_price"),
                                    output_field=MONEY_FIELD))
        )["v"] or Decimal("0.00")
        retail = batches.aggregate(
            v=Sum(ExpressionWrapper(F("quantity") * F("item__unit_price"),
                                    output_field=MONEY_FIELD))
        )["v"] or Decimal("0.00")
        return Response({
            "units": batches.aggregate(n=Sum("quantity"))["n"] or 0,
            "cost_value": cost,
            "retail_value": retail,
            "potential_margin": retail - cost,
        })


class StockBatchViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Consignments on the shelf. Read plus the non-quantity details.

    No create and no delete: stock arrives through the item's ``receive``
    action and leaves through a sale or an adjustment, so the movement ledger
    always accounts for the shelf.
    """

    serializer_class = StockBatchSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("item", "supplier")
    search_fields = ("batch_number", "supplier")
    ordering_fields = ("expiry_date", "created_at")

    def get_queryset(self):
        return StockBatch.objects.select_related("item")

    @action(detail=True, methods=["post"], url_path="adjust")
    def adjust(self, request, pk=None):
        """Set a batch to a counted quantity, or write it off. Admin only.

        The difference is logged as a movement with its reason, so a shrinkage
        is on the record rather than absorbed silently.
        """
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can adjust stock.")
        batch = self.get_object()
        data = _body(AdjustStockSerializer, request)
        kind = (StockMovement.Kind.WRITE_OFF if data["write_off"]
                else StockMovement.Kind.ADJUSTMENT)
        batch = adjust_stock(batch, data["quantity"], reason=data["reason"],
                             user=request.user, kind=kind)
        return success("Stock adjusted.", StockBatchSerializer(batch).data)

    @action(detail=False, methods=["get"], url_path="expiring")
    def expiring(self, request):
        """Stock expiring within ?days= (default 90), soonest first.

        Already-expired batches are included: they still sit on the shelf and
        still have to be pulled, and they are the ones that matter most.
        """
        try:
            days = int(request.query_params.get("days", 90))
        except ValueError:
            raise ValidationError({"days": "Must be a whole number of days."})
        cutoff = timezone.localdate() + timedelta(days=days)
        qs = self.get_queryset().filter(
            quantity__gt=0, expiry_date__isnull=False, expiry_date__lte=cutoff
        ).order_by("expiry_date")
        return Response(self.get_serializer(qs, many=True).data)


class StockMovementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """The stock ledger. Read-only by design — a movement is corrected by
    another movement, never by an edit."""

    serializer_class = StockMovementSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("item", "batch", "kind", "sale", "user")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return StockMovement.objects.select_related("item")


class SupplierViewSet(_PharmacyViewSet):
    """Who the pharmacy buys from. Staff read; the admin keeps the list."""

    model = Supplier
    serializer_class = SupplierSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active",)
    search_fields = ("name", "contact_person", "phone", "email")
    ordering_fields = ("name", "created_at")


class PurchaseOrderViewSet(_PharmacyViewSet):
    """Orders placed with suppliers, and the deliveries booked against them."""

    model = PurchaseOrder
    serializer_class = PurchaseOrderSerializer
    filterset_fields = ("status", "supplier")
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
        data = _body(ReceivePurchaseSerializer, request)
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


class HMOViewSet(_PharmacyViewSet):
    """Insurers the pharmacy bills. Coverage is money policy — admin writes."""

    model = HMO
    serializer_class = HMOSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active",)
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")


class HmoEnrollmentViewSet(_PharmacyViewSet):
    """Patients' scheme memberships — the cards staff check at the counter."""

    model = HmoEnrollment
    serializer_class = HmoEnrollmentSerializer
    filterset_fields = ("hmo", "patient", "is_active")
    search_fields = ("member_number", "plan")

    def get_queryset(self):
        return HmoEnrollment.objects.select_related("hmo", "patient")


class SaleViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                  mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Dispensing and taking payment.

    No update and no delete: a sale is a financial record. A mistake is
    reversed with ``cancel``, which puts the stock back and voids the claim.
    """

    serializer_class = SaleSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "payment_method", "patient", "served_by")
    search_fields = ("reference",)
    ordering_fields = ("created_at", "total")

    def get_queryset(self):
        return Sale.objects.select_related("patient", "served_by").prefetch_related(
            "lines"
        )

    def perform_create(self, serializer):
        # One transaction for the basket: a line that can't be filled rolls back
        # the stock the earlier lines already took.
        with transaction.atomic():
            serializer.save(served_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Take money against the patient's side of the bill."""
        sale = self.get_object()
        data = _body(SalePaymentSerializer, request)
        try:
            sale.record_payment(data["amount"])
        except ValueError as exc:
            raise ValidationError({"amount": str(exc)}) from exc
        return success("Payment recorded.", SaleSerializer(sale).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Reverse the sale and return every unit to the batch it came from."""
        sale = self.get_object()
        data = _body(SaleCancelSerializer, request)
        sale.cancel(reason=data.get("reason", ""), user=request.user)
        return success("Sale cancelled and stock returned.",
                       SaleSerializer(sale).data)

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
        zero = Decimal("0.00")
        billed = totals["billed"] or zero
        patient_share = totals["patient_share"] or zero
        collected = totals["collected"] or zero
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
            "hmo_share": totals["hmo_share"] or zero,
            "collected": collected,
            "outstanding": max(patient_share - collected, zero),
            "top_items": [
                {"item": row["item"], "name": row["item__name"],
                 "units": row["units"], "revenue": row["revenue"]}
                for row in top
            ],
        })


class ClaimViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """HMO claims from submission to settlement.

    Claims are raised by the sale that generated them, so there is no create
    here; every amount moves through a transition that says who decided it.
    """

    serializer_class = ClaimSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "hmo", "enrollment")
    search_fields = ("reference", "sale__reference")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return Claim.objects.select_related("hmo", "sale", "sale__patient")

    def _transition(self, request, call, message):
        claim = self.get_object()
        try:
            call(claim)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(message, ClaimSerializer(claim).data)

    def _require_admin(self, request):
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Send the claim to the insurer. Staff may do this."""
        return self._transition(request, lambda c: c.submit(), "Claim submitted.")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Record the insurer's approval, for all or part of the amount."""
        self._require_admin(request)
        data = _body(ClaimDecisionSerializer, request)
        return self._transition(
            request, lambda c: c.approve(data.get("amount")), "Claim approved."
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Record a refusal and why — a rejected claim can be resubmitted."""
        self._require_admin(request)
        data = _body(ClaimDecisionSerializer, request)
        return self._transition(
            request, lambda c: c.reject(data.get("reason", "")), "Claim rejected."
        )

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Bank a remittance against an approved claim."""
        self._require_admin(request)
        data = _body(ClaimPaymentSerializer, request)
        return self._transition(
            request, lambda c: c.record_payment(data["amount"]), "Payment recorded."
        )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """What each insurer owes: claimed, approved, paid, still outstanding."""
        start, end = _range(request)
        qs = _apply_range(self.get_queryset(), start, end).exclude(
            status=Claim.Status.CANCELLED
        )
        zero = Decimal("0.00")
        by_hmo = (qs.values("hmo", "hmo__name")
                  .annotate(claims=Count("id"), claimed=Sum("amount"),
                            approved=Sum("amount_approved"), paid=Sum("amount_paid"))
                  .order_by("-claimed"))
        totals = qs.aggregate(
            claims=Count("id"), claimed=Sum("amount"),
            approved=Sum("amount_approved"), paid=Sum("amount_paid"),
        )
        approved = totals["approved"] or zero
        paid = totals["paid"] or zero
        return Response({
            "claims": totals["claims"] or 0,
            "claimed": totals["claimed"] or zero,
            "approved": approved,
            "paid": paid,
            "outstanding": max(approved - paid, zero),
            "by_status": list(qs.values("status").annotate(
                n=Count("id"), amount=Sum("amount")).order_by("status")),
            "by_hmo": [
                {"hmo": row["hmo"], "name": row["hmo__name"],
                 "claims": row["claims"], "claimed": row["claimed"] or zero,
                 "approved": row["approved"] or zero, "paid": row["paid"] or zero,
                 "outstanding": max((row["approved"] or zero) - (row["paid"] or zero),
                                    zero)}
                for row in by_hmo
            ],
        })


class ClaimBatchViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    """Monthly claim schedules: one envelope per insurer, one remittance back.

    Creating a batch collects the insurer's unbatched open claims for the
    period, which is the whole job most months; ``add-claims`` is there for the
    ones added by hand afterwards.
    """

    serializer_class = ClaimBatchSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "hmo")
    search_fields = ("reference", "notes")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return ClaimBatch.objects.select_related("hmo")

    def perform_create(self, serializer):
        batch = serializer.save()
        claims = Claim.objects.filter(
            hmo=batch.hmo, batch__isnull=True, status__in=Claim.BATCHABLE,
        )
        if batch.period_start:
            claims = claims.filter(created_at__date__gte=batch.period_start)
        if batch.period_end:
            claims = claims.filter(created_at__date__lte=batch.period_end)
        batch.add_claims(list(claims))

    def _transition(self, call, message):
        batch = self.get_object()
        try:
            call(batch)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        batch.refresh_from_db()
        return success(message, ClaimBatchSerializer(batch).data)

    @action(detail=True, methods=["post"], url_path="add-claims")
    def add_claims(self, request, pk=None):
        """Add named claims (or sweep up the insurer's remaining open ones)."""
        batch = self.get_object()
        data = _body(AddClaimsSerializer, request)
        claims = data.get("claims") or list(Claim.objects.filter(
            hmo=batch.hmo, batch__isnull=True, status__in=Claim.BATCHABLE,
        ))
        try:
            moved = batch.add_claims(claims)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(f"{moved} claim(s) added to the batch.",
                       ClaimBatchSerializer(batch).data)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Send the schedule and every claim on it."""
        return self._transition(lambda b: b.submit(), "Batch submitted.")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Insurer accepted the whole schedule. Admin only."""
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")
        return self._transition(lambda b: b.approve_all(), "Batch approved.")

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Allocate one remittance across the batch's claims. Admin only."""
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")
        data = _body(ClaimPaymentSerializer, request)
        return self._transition(lambda b: b.record_payment(data["amount"]),
                                "Remittance allocated across the batch.")

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Withdraw the schedule and release its claims."""
        return self._transition(lambda b: b.cancel(), "Batch cancelled.")
