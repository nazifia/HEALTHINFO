from decimal import Decimal

from rest_framework import serializers

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    OutOfStock,
    PurchaseOrder,
    PurchaseOrderLine,
    Sale,
    SaleItem,
    StockBatch,
    StockItem,
    StockMovement,
    Supplier,
    claim_for_sale,
)


class StockItemSerializer(serializers.ModelSerializer):
    # Annotated by the viewset for lists; falls back to the model property so a
    # single retrieve is still correct.
    quantity_on_hand = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    medication_name = serializers.CharField(
        source="medication.generic_name", read_only=True
    )

    class Meta:
        model = StockItem
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def get_quantity_on_hand(self, obj) -> int:
        return getattr(obj, "stock_on_hand", None) or obj.quantity_on_hand

    def get_is_low_stock(self, obj) -> bool:
        return self.get_quantity_on_hand(obj) <= obj.reorder_level


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class StockBatchSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockBatch
        exclude = ("tenant",)
        # Quantity moves through receipts, sales and adjustments only — never by
        # editing the row, or the movement ledger would stop explaining the shelf.
        read_only_fields = ("quantity", "quantity_received", "created_at",
                            "updated_at")


class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = StockMovement
        exclude = ("tenant",)


class ReceiveStockSerializer(serializers.Serializer):
    """Booking a consignment in against an item."""

    quantity = serializers.IntegerField(min_value=1)
    batch_number = serializers.CharField(max_length=100)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    cost_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects, required=False, allow_null=True
    )


class AdjustStockSerializer(serializers.Serializer):
    """A counted quantity plus the reason it differs from the books."""

    quantity = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=255)
    write_off = serializers.BooleanField(
        default=False,
        help_text="Log as a write-off (expired/damaged/lost) instead of a count "
                  "correction.",
    )


class HMOSerializer(serializers.ModelSerializer):
    class Meta:
        model = HMO
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value


class HmoEnrollmentSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    effective_coverage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = HmoEnrollment
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if value is not None and not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value


class SaleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2,
                                          read_only=True)

    class Meta:
        model = SaleItem
        exclude = ("tenant", "sale")


class SaleLineInputSerializer(serializers.Serializer):
    """One requested line. Batches are chosen by the server (first-expiry-first-
    out), so the client asks for an item and a quantity, never for a batch."""

    item = serializers.PrimaryKeyRelatedField(queryset=StockItem.objects)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    discount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0.00")
    )


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleItemSerializer(many=True, read_only=True)
    # Write-only request lines; the stored lines come back under ``lines``.
    items = SaleLineInputSerializer(many=True, write_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    served_by_name = serializers.CharField(source="served_by.username",
                                           read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2,
                                           read_only=True)
    claim_id = serializers.IntegerField(source="claim.id", read_only=True)

    class Meta:
        model = Sale
        exclude = ("tenant",)
        # Every money field is derived from the lines and the coverage — a
        # client that could post its own total could bill an HMO anything.
        read_only_fields = ("reference", "served_by", "status", "subtotal",
                            "discount", "total", "patient_payable", "hmo_payable",
                            "amount_paid", "created_at", "updated_at")

    def validate(self, attrs):
        method = attrs.get("payment_method", Sale.PaymentMethod.CASH)
        enrollment = attrs.get("enrollment")
        patient = attrs.get("patient")
        if method == Sale.PaymentMethod.HMO:
            if not enrollment and patient:
                # The counter names the patient, not their card number: find the
                # scheme they are on. Only when there is exactly one valid
                # membership — a patient on two schemes must be told which.
                valid = [e for e in patient.hmo_enrollments.select_related("hmo")
                         if e.is_valid]
                if len(valid) == 1:
                    enrollment = attrs["enrollment"] = valid[0]
                elif len(valid) > 1:
                    raise serializers.ValidationError(
                        {"enrollment": "That patient is on more than one scheme — "
                                       "say which membership to bill."}
                    )
            if not enrollment:
                raise serializers.ValidationError(
                    {"enrollment": "An HMO sale needs the patient's scheme membership."}
                )
            if not enrollment.is_valid:
                raise serializers.ValidationError(
                    {"enrollment": "That membership is inactive or out of date."}
                )
            if patient and enrollment.patient_id != patient.id:
                raise serializers.ValidationError(
                    {"enrollment": "That membership belongs to a different patient."}
                )
            attrs["patient"] = patient or enrollment.patient
        elif enrollment:
            raise serializers.ValidationError(
                {"enrollment": "Only an HMO sale carries a scheme membership."}
            )
        if not attrs.get("items"):
            raise serializers.ValidationError({"items": "A sale needs at least one item."})
        return attrs

    def create(self, validated_data):
        """Dispense the whole basket or none of it, then raise any HMO claim.

        Wrapped in the request's atomic block by the viewset, so a line that
        can't be filled rolls the earlier lines' stock back.
        """
        lines = validated_data.pop("items")
        sale = Sale(**validated_data)
        sale.save()
        user = sale.served_by
        for line in lines:
            try:
                sale.add_line(
                    line["item"], line["quantity"],
                    unit_price=line.get("unit_price"),
                    discount=line.get("discount") or Decimal("0.00"),
                    user=user,
                )
            except OutOfStock as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc
        claim_for_sale(sale)
        sale.refresh_from_db()
        return sale


class SalePaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                       min_value=Decimal("0.01"))


class SaleCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                    default="")


class ClaimSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    sale_reference = serializers.CharField(source="sale.reference", read_only=True)
    patient_name = serializers.CharField(source="sale.patient.full_name",
                                          read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2,
                                            read_only=True)

    class Meta:
        model = Claim
        exclude = ("tenant",)
        # A claim is raised from a sale, never typed in: the amount is the
        # insurer's share of what was actually dispensed.
        read_only_fields = ("sale", "hmo", "enrollment", "reference", "amount",
                            "amount_approved", "amount_paid", "status",
                            "submitted_at", "settled_at", "rejection_reason",
                            "created_at", "updated_at")


class ClaimDecisionSerializer(serializers.Serializer):
    """The insurer's answer: an approved amount, or a reason for refusing."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                       required=False, allow_null=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                    default="")


class ClaimPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                       min_value=Decimal("0.01"))


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    outstanding = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseOrderLine
        exclude = ("tenant", "order")
        # Received counts come from bookings against the line, never from a PATCH.
        read_only_fields = ("quantity_received", "created_at", "updated_at")


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    # Write-only order lines; the stored lines come back under ``lines``.
    items = PurchaseOrderLineSerializer(many=True, write_only=True, required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    total_cost = serializers.DecimalField(max_digits=14, decimal_places=2,
                                          read_only=True)

    class Meta:
        model = PurchaseOrder
        exclude = ("tenant",)
        read_only_fields = ("reference", "status", "ordered_by", "created_at",
                            "updated_at")

    def create(self, validated_data):
        lines = validated_data.pop("items", [])
        order = PurchaseOrder(**validated_data)
        order.save()
        for line in lines:
            PurchaseOrderLine.all_objects.create(tenant=order.tenant, order=order,
                                                 **line)
        return order

    def update(self, instance, validated_data):
        """Lines are replaced wholesale, and only while the order is a draft.

        Editing a line on an order the supplier already has would make the
        received counts describe an order nobody placed.
        """
        lines = validated_data.pop("items", None)
        if lines is not None:
            if instance.status != PurchaseOrder.Status.DRAFT:
                raise serializers.ValidationError(
                    {"items": "Lines can only be changed while the order is a draft."}
                )
            PurchaseOrderLine.all_objects.filter(order=instance).delete()
            for line in lines:
                PurchaseOrderLine.all_objects.create(
                    tenant=instance.tenant, order=instance, **line
                )
        return super().update(instance, validated_data)


class ReceivePurchaseSerializer(serializers.Serializer):
    """A delivery against one order line."""

    line = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrderLine.objects)
    quantity = serializers.IntegerField(min_value=1)
    batch_number = serializers.CharField(max_length=100)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    unit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )


class ClaimBatchSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    totals = serializers.DictField(read_only=True)

    class Meta:
        model = ClaimBatch
        exclude = ("tenant",)
        read_only_fields = ("reference", "status", "submitted_at", "created_at",
                            "updated_at")


class AddClaimsSerializer(serializers.Serializer):
    """Which claims to bundle. Left empty, the batch collects every unbatched
    open claim for its insurer inside its period."""

    claims = serializers.PrimaryKeyRelatedField(
        queryset=Claim.objects, many=True, required=False
    )
