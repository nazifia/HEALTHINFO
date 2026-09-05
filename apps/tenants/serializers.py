from rest_framework import serializers

from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    # The bare jurisdiction pk says nothing on screen; the name does.
    jurisdiction_name = serializers.CharField(
        source="jurisdiction.name", read_only=True, default=None
    )

    class Meta:
        model = Tenant
        fields = (
            "id", "name", "slug", "kind", "address", "contact", "logo", "domain",
            "jurisdiction", "jurisdiction_name", "subscription_plan",
            "subscription_status",
            "status", "user_count", "created_at", "updated_at",
        )
        read_only_fields = ("user_count", "jurisdiction_name", "created_at", "updated_at")
