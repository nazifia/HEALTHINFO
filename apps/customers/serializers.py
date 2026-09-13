from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import normalize_phone
from config.serializers import NamedRelationsMixin

from .models import Customer, WalletTransaction


class WalletTransactionSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        exclude = ("tenant",)
        read_only_fields = ("customer", "txn_type", "method", "amount", "note",
                            "created_at", "updated_at")


class CustomerSerializer(serializers.ModelSerializer):
    total_purchases = serializers.DecimalField(max_digits=14, decimal_places=2,
                                               read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    prescriber_name = serializers.CharField(source="prescriber.name", read_only=True)

    class Meta:
        model = Customer
        exclude = ("tenant",)
        # Balances move through top-ups, purchases and refunds. A client that
        # could PATCH a wallet could hand itself money.
        read_only_fields = ("wallet_balance", "outstanding_debt", "last_visit",
                            "created_at", "updated_at")

    def validate_phone(self, value):
        # unique_together (tenant, phone) can't be checked by DRF here: tenant
        # is stamped server-side. Check the one shape the model stores against
        # this tenant's rows, so a respelt number is a 400, not a 500.
        value = normalize_phone(value)
        clash = Customer.objects.filter(phone=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                "A customer with this phone number already exists."
            )
        return value


class WalletInputSerializer(serializers.Serializer):
    """Money onto or off the wallet, and how it arrived."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=WalletTransaction.Method.choices,
                                     required=False, default=WalletTransaction.Method.CASH)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True,
                                 default="")
