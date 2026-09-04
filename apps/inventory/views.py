"""Inventory API.

Stock only ever moves through a named door: a receipt, a sale, an adjustment,
a stock check or a transfer. There is deliberately no way to PATCH a batch
quantity — every figure a client can change is an input to the shelf, never
the shelf itself.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
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
    OutOfStock,
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Supplier,
    TransferRequest,
    adjust_stock,
    receive_stock,
)
from .serializers import (
    AdjustStockSerializer,
    CountLineSerializer,
    ReceiveStockSerializer,
    StockBatchSerializer,
    StockCheckSerializer,
    StockItemSerializer,
    StockMovementSerializer,
    SupplierSerializer,
    TransferDecisionSerializer,
    TransferRequestSerializer,
    WriteOffSerializer,
)

MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def body(serializer_class, request):
    """Validate an action's body and return its data, or raise DRF's 400."""
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PharmacyViewSet(viewsets.ModelViewSet):
    """Tenant-scoped, pharmacy-staff-only base.

    ``model`` supplies the per-request queryset: the manager is re-run every
    time so tenant scoping is never frozen onto the class.
    """

    model = None
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return self.model.objects.all()


class SupplierViewSet(PharmacyViewSet):
    """Who the pharmacy buys from. Staff read; the admin keeps the list."""

    model = Supplier
    serializer_class = SupplierSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active",)
    search_fields = ("name", "contact_person", "phone", "email")
    ordering_fields = ("name", "created_at")


class StockItemViewSet(PharmacyViewSet):
    """The pharmacy's item list — what it sells and what it charges.

    Staff read and dispense against it; only the pharmacy admin edits a price,
    a reorder level or the list itself.
    """

    model = StockItem
    serializer_class = StockItemSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("form", "store", "branch", "is_active",
                        "prescription_only", "medication")
    search_fields = ("name", "brand", "sku", "barcode", "gtin")
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
        data = body(ReceiveStockSerializer, request)
        batch = receive_stock(
            item, data["quantity"], batch_number=data["batch_number"],
            expiry_date=data.get("expiry_date"), cost_price=data.get("cost_price"),
            supplier=data.get("supplier"), user=request.user,
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

    @action(detail=False, methods=["get"], url_path="barcode")
    def barcode(self, request):
        """Look one item up by the code on the box — what a scanner asks for."""
        code = (request.query_params.get("code") or "").strip()
        if not code:
            raise ValidationError({"code": "Scan or type a barcode to look up."})
        item = self.get_queryset().filter(barcode=code).first()
        if item is None:
            item = self.get_queryset().filter(gtin=code).first()
        if item is None:
            return Response({"detail": "No item carries that code."}, status=404)
        return Response(self.get_serializer(item).data)

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
    search_fields = ("batch_number",)
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
        data = body(AdjustStockSerializer, request)
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

    @action(detail=False, methods=["post"], url_path="write-off-expired")
    def write_off_expired(self, request):
        """Pull every expired batch off the shelf in one go. Admin only.

        Expired stock still counts as stock on hand until someone writes it
        off, which is what makes a valuation wrong. Each batch gets its own
        WRITE_OFF movement, so the loss is attributable batch by batch.
        """
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can write stock off.")
        data = body(WriteOffSerializer, request)
        as_of = data.get("as_of") or timezone.localdate()
        batches = list(StockBatch.objects.filter(
            quantity__gt=0, expiry_date__isnull=False, expiry_date__lt=as_of
        ).select_related("item"))
        units = 0
        value = Decimal("0.00")
        with transaction.atomic():
            for batch in batches:
                units += batch.quantity
                value += batch.quantity * batch.cost_price
                adjust_stock(batch, 0, reason=data["reason"], user=request.user,
                             kind=StockMovement.Kind.WRITE_OFF)
        return success(
            f"Wrote off {units} unit(s) across {len(batches)} batch(es).",
            {"batches": len(batches), "units": units,
             "cost_value": value.quantize(Decimal("0.01"))},
        )


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


class StockCheckViewSet(PharmacyViewSet):
    """Stocktakes: raise a count, enter what was found, then apply the gaps.

    The expected quantity is snapshotted when a line is raised, so a sale that
    happens mid-count doesn't silently move the target someone is counting
    against.
    """

    model = StockCheck
    serializer_class = StockCheckSerializer
    filterset_fields = ("status", "store", "branch")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return StockCheck.objects.select_related("created_by").prefetch_related(
            "lines__item"
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="count")
    def count(self, request, pk=None):
        """Record what was found, line by line. Repeatable until it is closed.

        Counting an item that isn't on the sheet adds it, because the thing
        you found on the shelf that the books don't know about is exactly what
        a stocktake is for.
        """
        check = self.get_object()
        if check.status in (StockCheck.Status.COMPLETED,
                            StockCheck.Status.CANCELLED):
            raise ValidationError(
                {"status": f"This stock check is already {check.status}."}
            )
        serializer = CountLineSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for row in serializer.validated_data:
            item = row["item"]
            line, created = StockCheckItem.all_objects.get_or_create(
                tenant=check.tenant, stock_check=check, item=item,
                defaults={"expected_quantity": item.quantity_on_hand},
            )
            line.actual_quantity = row["quantity"]
            line.notes = row.get("notes", "")
            line.save(update_fields=["actual_quantity", "notes", "updated_at"])
        if check.status == StockCheck.Status.PENDING:
            check.status = StockCheck.Status.IN_PROGRESS
            check.save(update_fields=["status", "updated_at"])
        check.refresh_from_db()
        return success(f"{len(serializer.validated_data)} line(s) counted.",
                       StockCheckSerializer(check).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Apply every counted line and close the check. Admin only.

        Applying a count writes stock, so it sits with whoever may already
        adjust a batch by hand.
        """
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied(
                "Only the pharmacy admin can apply a stock check."
            )
        check = self.get_object()
        try:
            check.complete(user=request.user)
        except OutOfStock as exc:
            raise ValidationError({"lines": str(exc)}) from exc
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success("Stock check applied and closed.",
                       StockCheckSerializer(check).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Abandon the count. Nothing is written to stock."""
        check = self.get_object()
        try:
            check.cancel()
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success("Stock check cancelled.", StockCheckSerializer(check).data)


class TransferRequestViewSet(PharmacyViewSet):
    """Stock asked for from the other store, and what was actually sent."""

    model = TransferRequest
    serializer_class = TransferRequestSerializer
    filterset_fields = ("status", "from_item", "to_item")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return TransferRequest.objects.select_related("from_item", "to_item")

    def perform_create(self, serializer):
        serializer.save(requested_by=self.request.user)

    def _transition(self, call, message):
        request_row = self.get_object()
        try:
            call(request_row)
        except OutOfStock as exc:
            raise ValidationError({"quantity": str(exc)}) from exc
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        request_row.refresh_from_db()
        return success(message, TransferRequestSerializer(request_row).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Agree the move; the stock crosses in the same transaction."""
        data = body(TransferDecisionSerializer, request)
        return self._transition(
            lambda t: t.approve(data.get("quantity"), user=request.user),
            "Transfer approved and stock moved.",
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Refuse it, with a reason the asking store can read."""
        data = body(TransferDecisionSerializer, request)
        return self._transition(
            lambda t: t.reject(user=request.user, reason=data.get("reason", "")),
            "Transfer rejected.",
        )

    @action(detail=True, methods=["post"], url_path="receive")
    def receive(self, request, pk=None):
        """The receiving store confirms the units are on its shelf."""
        return self._transition(lambda t: t.receive(), "Transfer received.")
