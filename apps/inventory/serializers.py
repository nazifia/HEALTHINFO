from django.db import transaction
from rest_framework import serializers

from config.serializers import NamedRelationsMixin

from .models import (
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Supplier,
    TransferRequest,
    marked_up,
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
    # The shelf count typed on the item form itself — booked in as a dated
    # batch through receive_stock, so the ledger still explains the figure.
    # Optional on both create and edit: on an edit it adds to what is there.
    # Negative takes units off first-expiry-first-out, logged as an adjustment.
    add_stock = serializers.IntegerField(
        required=False, write_only=True,
        label="Add or remove stock",
        help_text="Units to put on the shelf now (negative to remove). "
                  "Added to the quantity on hand.",
    )

    class Meta:
        model = StockItem
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")
        # A catalog drug names the row itself; the name is typed only for
        # stock the catalog doesn't carry.
        extra_kwargs = {"name": {"required": False, "allow_blank": True}}

    def validate(self, attrs):
        if "name" in attrs or not self.instance:
            medication = attrs.get("medication") or getattr(self.instance, "medication", None)
            if not attrs.get("name", "").strip():
                if not medication:
                    raise serializers.ValidationError(
                        {"name": "Pick a medication or type a name."})
                attrs["name"] = medication.generic_name
        return attrs

    def _book_in(self, item, quantity):
        if quantity:
            from django.utils import timezone
            from .models import OutOfStock, StockMovement, receive_stock, take_stock
            user = getattr(self.context.get("request"), "user", None)
            if quantity > 0:
                receive_stock(item, quantity,
                              batch_number=f"ADD-{timezone.now():%Y%m%d}",
                              cost_price=item.cost_price, user=user)
            else:
                try:
                    take_stock(item, -quantity,
                               kind=StockMovement.Kind.ADJUSTMENT,
                               reason="Quantity corrected on the item", user=user)
                except OutOfStock as exc:
                    raise serializers.ValidationError({"add_stock": str(exc)})
            # The list annotation on an edited row is now stale; the
            # property recounts.
            if hasattr(item, "stock_on_hand"):
                del item.stock_on_hand

    @transaction.atomic
    def create(self, validated_data):
        quantity = validated_data.pop("add_stock", 0)
        item = super().create(validated_data)
        self._book_in(item, quantity)
        return item

    @transaction.atomic
    def update(self, instance, validated_data):
        quantity = validated_data.pop("add_stock", 0)
        # A changed markup or cost re-prices the item from cost, unless the
        # same edit sets the sell price itself.
        markup = validated_data.get("markup", instance.markup)
        cost = validated_data.get("cost_price", instance.cost_price)
        if (markup and (markup != instance.markup or cost != instance.cost_price)
                and validated_data.get("unit_price", instance.unit_price)
                == instance.unit_price):
            validated_data["unit_price"] = marked_up(cost, markup)
        item = super().update(instance, validated_data)
        self._book_in(item, quantity)
        return item

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


class StockMovementSerializer(NamedRelationsMixin, serializers.ModelSerializer):
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


class StockCheckSerializer(NamedRelationsMixin, serializers.ModelSerializer):
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


class TransferRequestSerializer(NamedRelationsMixin, serializers.ModelSerializer):
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
