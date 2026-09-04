from decimal import Decimal

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.accounts.serializers import TenantUserField
from apps.inventory.models import OutOfStock, StockItem, Supplier
from apps.inventory.serializers import StockBatchSerializer  # noqa: F401

from .models import (
    Cashier,
    DispensingLog,
    Expense,
    ExpenseCategory,
    Notification,
    PaymentRequest,
    PaymentRequestItem,
    PurchaseOrder,
    PurchaseOrderLine,
    ReturnRecord,
    Sale,
    SaleItem,
    SalePayment,
    TillSession,
)

ZERO = Decimal("0.00")


class CashierSerializer(serializers.ModelSerializer):
    # OneToOne in the DB: keep the uniqueness check the auto-generated field
    # carried, on every row (all_objects) since the constraint is global.
    user = TenantUserField(
        validators=[UniqueValidator(queryset=Cashier.all_objects.all())]
    )
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Cashier
        exclude = ("tenant",)
        read_only_fields = ("code", "created_at", "updated_at")


class SaleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    batch_number = serializers.CharField(source="batch.batch_number", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2,
                                          read_only=True)
    returnable = serializers.IntegerField(read_only=True)

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
        max_digits=12, decimal_places=2, required=False, default=ZERO
    )


class SalePaymentSerializer(serializers.ModelSerializer):
    """One payment as it was taken: the form it arrived in and its drawer."""

    taken_by_name = serializers.CharField(source="taken_by.username", read_only=True)

    class Meta:
        model = SalePayment
        fields = ("id", "method", "tendered", "applied", "change", "till_session",
                  "taken_by_name", "created_at")


class SalePaymentInputSerializer(serializers.Serializer):
    """What the counter says: how much was handed over, and in what form."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      min_value=Decimal("0.01"))
    # Left out, the sale's own method applies - an insured sale's co-payment is
    # taken as cash, which is how it reaches the drawer.
    method = serializers.ChoiceField(choices=SalePayment.Method.choices,
                                     required=False)


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleItemSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    # Write-only request lines; the stored lines come back under ``lines``.
    items = SaleLineInputSerializer(many=True, write_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    served_by_name = serializers.CharField(source="served_by.username",
                                           read_only=True)
    buyer = serializers.CharField(read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2,
                                           read_only=True)
    change_due = serializers.DecimalField(max_digits=12, decimal_places=2,
                                          read_only=True)
    claim_id = serializers.IntegerField(source="claim.id", read_only=True)

    class Meta:
        model = Sale
        exclude = ("tenant",)
        # Every money field is derived from the lines and the coverage — a
        # client that could post its own total could bill an HMO anything.
        read_only_fields = ("reference", "served_by", "status", "subtotal",
                            "discount", "total", "patient_payable", "hmo_payable",
                            "amount_paid", "amount_tendered", "created_at",
                            "updated_at")

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
        if method == Sale.PaymentMethod.WALLET and not attrs.get("customer"):
            raise serializers.ValidationError(
                {"customer": "A wallet sale needs the customer whose wallet pays."}
            )
        if not attrs.get("items"):
            raise serializers.ValidationError({"items": "A sale needs at least one item."})
        return attrs

    def create(self, validated_data):
        """Dispense the whole basket or none of it, then raise any HMO claim.

        Wrapped in the request's atomic block by the viewset, so a line that
        can't be filled rolls the earlier lines' stock back.
        """
        from apps.pharmacy.models import claim_for_sale

        lines = validated_data.pop("items")
        sale = Sale(**validated_data)
        sale.save()
        user = sale.served_by
        for line in lines:
            try:
                sale.add_line(
                    line["item"], line["quantity"],
                    unit_price=line.get("unit_price"),
                    discount=line.get("discount") or ZERO,
                    user=user,
                )
            except OutOfStock as exc:
                raise serializers.ValidationError({"items": str(exc)}) from exc
        claim_for_sale(sale)
        if sale.rx_id:
            # The prescriber earns on what their script actually sold, so this
            # is raised from the sale rather than when the script was written.
            sale.rx.raise_prescriber_dues(sale)
        sale.refresh_from_db()
        return sale


class SaleCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   default="")


class ReturnInputSerializer(serializers.Serializer):
    """One line coming back over the counter."""

    line = serializers.PrimaryKeyRelatedField(queryset=SaleItem.objects)
    quantity = serializers.IntegerField(min_value=1)
    refund_method = serializers.ChoiceField(
        choices=ReturnRecord.RefundMethod.choices,
        default=ReturnRecord.RefundMethod.WALLET,
    )
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True,
                                   default="")


class ReturnRecordSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="line.name", read_only=True)
    sale_reference = serializers.CharField(source="sale.reference", read_only=True)

    class Meta:
        model = ReturnRecord
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class TillSessionSerializer(serializers.ModelSerializer):
    """The drawer as the counter sees it: what should be in it, and what was."""

    opened_by_name = serializers.CharField(source="opened_by.username",
                                           read_only=True)
    # Totalled from the drawer's payment rows, not stored on the session.
    cash_in = serializers.DecimalField(max_digits=12, decimal_places=2,
                                       read_only=True)
    change_out = serializers.DecimalField(max_digits=12, decimal_places=2,
                                          read_only=True)
    cash_out = serializers.DecimalField(max_digits=12, decimal_places=2,
                                        read_only=True)
    expected_amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                               read_only=True)
    variance = serializers.DecimalField(max_digits=12, decimal_places=2,
                                        read_only=True)

    class Meta:
        model = TillSession
        exclude = ("tenant",)
        # A cashier opens a drawer with a float and closes it with a count;
        # every other figure is booked by the sales that went through it.
        read_only_fields = ("opened_by", "status", "counted_amount", "closed_at",
                            "created_at", "updated_at")


class TillCloseSerializer(serializers.Serializer):
    """The counted cash, and why it differs if it does."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      min_value=Decimal("0"))
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                  default="")


class DispensingLogSerializer(serializers.ModelSerializer):
    dispenser = serializers.CharField(source="user.username", read_only=True)
    sale_reference = serializers.CharField(source="sale.reference", read_only=True)

    class Meta:
        model = DispensingLog
        exclude = ("tenant",)


class PaymentRequestItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2,
                                        read_only=True)

    class Meta:
        model = PaymentRequestItem
        exclude = ("tenant", "request")
        read_only_fields = ("created_at", "updated_at")


class PaymentRequestSerializer(serializers.ModelSerializer):
    lines = PaymentRequestItemSerializer(many=True, read_only=True)
    items = PaymentRequestItemSerializer(many=True, write_only=True)
    dispenser_name = serializers.CharField(source="dispenser.username",
                                           read_only=True)
    cashier_name = serializers.CharField(source="cashier.name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = PaymentRequest
        exclude = ("tenant",)
        read_only_fields = ("reference", "dispenser", "cashier", "status",
                            "total_amount", "sale", "created_at", "updated_at")

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("A request needs at least one item.")
        return value

    def create(self, validated_data):
        lines = validated_data.pop("items", [])
        request_row = PaymentRequest(**validated_data)
        request_row.save()
        for line in lines:
            PaymentRequestItem.all_objects.create(
                tenant=request_row.tenant, request=request_row, **line
            )
        return request_row.recalculate()

    def update(self, instance, validated_data):
        """Lines are replaced wholesale, and only while nobody has taken it."""
        lines = validated_data.pop("items", None)
        if lines is not None:
            if instance.status != PaymentRequest.Status.PENDING:
                raise serializers.ValidationError(
                    {"items": "A request a cashier has taken can no longer change."}
                )
            PaymentRequestItem.all_objects.filter(request=instance).delete()
            for line in lines:
                PaymentRequestItem.all_objects.create(
                    tenant=instance.tenant, request=instance, **line
                )
        instance = super().update(instance, validated_data)
        return instance.recalculate()


class CompleteRequestSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   default="")


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Expense
        exclude = ("tenant",)
        read_only_fields = ("created_by", "created_at", "updated_at")


class NotificationSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = Notification
        exclude = ("tenant",)
        read_only_fields = ("user", "kind", "priority", "title", "message", "item",
                            "created_at", "updated_at")


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


class SupplierRefSerializer(serializers.ModelSerializer):
    """Suppliers as an order needs to name them — the full record is in
    ``inventory``."""

    class Meta:
        model = Supplier
        fields = ("id", "name", "phone", "is_active")
