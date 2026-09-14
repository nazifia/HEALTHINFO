from rest_framework import serializers

from apps.accounts.serializers import TenantUserField

from .models import Branch, Shift


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class ShiftSerializer(serializers.ModelSerializer):
    # Only this tenant's staff go on its roster.
    user = TenantUserField()
    username = serializers.CharField(source="user.username", read_only=True)
    # A shift with no branch is the whole facility, so this is "" rather than
    # null — the roster card prints it straight.
    branch_name = serializers.SerializerMethodField()

    def get_branch_name(self, obj):
        return obj.branch.name if obj.branch else ""

    class Meta:
        model = Shift
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate(self, attrs):
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError(
                {"ends_at": "A shift must end after it starts."}
            )
        return attrs
