from decimal import Decimal

from rest_framework import serializers

from .models import CommissionConfig


class CommissionConfigSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = CommissionConfig
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_rate(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Rate must be between 0 and 100.")
        return value
