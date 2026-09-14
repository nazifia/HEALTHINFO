import base64
import binascii

from rest_framework import serializers

from .models import MAX_LOGO_BYTES, Tenant


def clean_logo(value):
    """A data: URL for a PNG/JPEG/WebP under MAX_LOGO_BYTES, or "" to clear it.

    Checked here rather than trusted from the client because the string lands
    verbatim inside an <img src> on every receipt.
    """
    if not value:
        return ""
    if not isinstance(value, str):
        raise serializers.ValidationError({"logo": "Send the image as a data URL."})
    header, _, payload = value.partition(",")
    if header not in ("data:image/png;base64", "data:image/jpeg;base64",
                      "data:image/webp;base64"):
        raise serializers.ValidationError({"logo": "Use a PNG, JPEG or WebP image."})
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise serializers.ValidationError({"logo": "That image is not valid base64."})
    if len(raw) > MAX_LOGO_BYTES:
        raise serializers.ValidationError(
            {"logo": f"Logo must be under {MAX_LOGO_BYTES // 1024} KB."}
        )
    return value


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
            "status", "idle_logout_minutes", "user_count", "created_at", "updated_at",
        )
        read_only_fields = ("user_count", "jurisdiction_name", "created_at", "updated_at")

    # The platform admin brands a tenant from its record; same checks as the
    # tenant's own settings endpoint. DRF wraps the message under the field.
    def validate_logo(self, value):
        try:
            return clean_logo(value)
        except serializers.ValidationError as e:
            raise serializers.ValidationError(e.detail["logo"])
