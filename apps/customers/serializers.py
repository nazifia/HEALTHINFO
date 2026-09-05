from decimal import Decimal

from rest_framework import serializers

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


class WalletInputSerializer(serializers.Serializer):
    """Money onto or off the wallet, and how it arrived."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=WalletTransaction.Method.choices,
                                     required=False, default=WalletTransaction.Method.CASH)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True,
                                 default="")
