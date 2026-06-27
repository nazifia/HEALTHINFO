from rest_framework import serializers

from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tenant
        fields = (
            "id", "name", "slug", "address", "contact", "logo", "domain",
            "jurisdiction", "subscription_plan", "subscription_status",
            "status", "user_count", "created_at", "updated_at",
        )
        read_only_fields = ("user_count", "created_at", "updated_at")
