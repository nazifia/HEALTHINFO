from rest_framework import serializers

from .models import AuditLog


class TransitionSerializer(serializers.Serializer):
    to = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = (
            "id", "user", "from_status", "to_status", "note", "created_at"
        )
