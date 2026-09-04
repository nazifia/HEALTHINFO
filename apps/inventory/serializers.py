from rest_framework import serializers

from .models import (
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Supplier,
    TransferRequest,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class StockItemSerializer(serializers.ModelSerializer):
    # Annotated by the viewset for lists; falls back to the model property so a
    # single retrieve is still correct.
    quantity_on_hand = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    medication_name = serializers.CharField(
        source="medication.generic_name", read_only=True
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = StockItem
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def get_quantity_on_hand(self, obj) -> int:
        return getattr(obj, "stock_on_hand", None) or obj.quantity_on_hand

    def get_is_low_stock(self, obj) -> bool:
        return self.get_quantity_on_hand(obj) <= obj.reorder_level


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


class StockCheckItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    discrepancy = serializers.IntegerField(read_only=True)
    cost_difference = serializers.DecimalField(max_digits=12, decimal_places=2,
                                               read_only=True)

    class Meta:
        model = StockCheckItem
        exclude = ("tenant", "stock_check")
        # Expected is what the shelf said when the line was raised; the count
        # is the only figure the counter supplies.
        read_only_fields = ("expected_quantity", "status", "created_at",
                            "updated_at")


class StockCheckSerializer(serializers.ModelSerializer):
    lines = StockCheckItemSerializer(many=True, read_only=True)
    # Write-only: which items to count. Expected quantities are read off the
    # shelf here, not sent by the client — otherwise the count is checked
    # against a number the client chose.
    items = serializers.PrimaryKeyRelatedField(
        queryset=StockItem.objects, many=True, write_only=True, required=False
    )
    totals = serializers.DictField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.username",
                                            read_only=True)

    class Meta:
        model = StockCheck
        exclude = ("tenant",)
        read_only_fields = ("status", "created_by", "approved_by", "approved_at",
                            "created_at", "updated_at")

    def create(self, validated_data):
        items = validated_data.pop("items", [])
        check = StockCheck(**validated_data)
        check.save()
        for item in items:
            StockCheckItem.all_objects.create(
                tenant=check.tenant, stock_check=check, item=item,
                expected_quantity=item.quantity_on_hand,
            )
        return check


class CountLineSerializer(serializers.Serializer):
    """One counted line: the item, and how many were actually there."""

    item = serializers.PrimaryKeyRelatedField(queryset=StockItem.objects)
    quantity = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                  default="")


class TransferRequestSerializer(serializers.ModelSerializer):
    from_item_name = serializers.CharField(source="from_item.name", read_only=True)
    to_item_name = serializers.CharField(source="to_item.name", read_only=True)
    direction = serializers.CharField(read_only=True)

    class Meta:
        model = TransferRequest
        exclude = ("tenant",)
        read_only_fields = ("status", "approved_quantity", "requested_by",
                            "approved_by", "created_at", "updated_at")

    def validate(self, attrs):
        source = attrs.get("from_item")
        target = attrs.get("to_item")
        if source and target:
            if source.pk == target.pk:
                raise serializers.ValidationError(
                    {"to_item": "A transfer needs two different item lines."}
                )
            if source.store == target.store:
                raise serializers.ValidationError(
                    {"to_item": "Both lines are in the same store; nothing to move."}
                )
        return attrs


class TransferDecisionSerializer(serializers.Serializer):
    """The sending store's answer: how many it can actually spare, or why not."""

    quantity = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   default="")


class WriteOffSerializer(serializers.Serializer):
    """Pull expired stock off the shelf, with a reason on every batch."""

    reason = serializers.CharField(max_length=255, required=False,
                                   default="Expired stock written off")
    as_of = serializers.DateField(required=False, allow_null=True)
