from rest_framework import serializers

from .models import AuditLog


class TransitionSerializer(serializers.Serializer):
    to = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AuditLogSerializer(serializers.ModelSerializer):
    # A trail naming user ids answers nothing on its own. default=None because
    # the FK is SET_NULL: a deleted account leaves its rows behind.
    user_phone = serializers.CharField(
        source="user.phone", read_only=True, default=None
    )

    class Meta:
        model = AuditLog
        fields = (
            "id", "user", "user_phone", "from_status", "to_status", "note",
            "created_at",
        )
