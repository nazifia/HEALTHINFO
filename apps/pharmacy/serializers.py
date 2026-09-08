from decimal import Decimal

from rest_framework import serializers

from apps.accounts.permissions import INSURER_ROLES

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    HmoItemRule,
    PreAuthorization,
    PreAuthorizationItem,
)


class HMOSerializer(serializers.ModelSerializer):
    class Meta:
        model = HMO
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value

    def validate_tariff(self, value):
        if value is not None and value < Decimal("0"):
            raise serializers.ValidationError("A tariff cannot be negative.")
        return value

    def validate_hmo(self, value):
        # An insurer keeps its own price list and nobody else's. The view
        # already refuses an edit to another scheme's row; this refuses a new
        # row filed under someone else's scheme, which has no row yet to check.
        user = self.context["request"].user
        if user.is_authenticated and user.role in INSURER_ROLES:
            if value.pk != user.hmo_id:
                raise serializers.ValidationError(
                    "You can only price your own scheme's list."
                )
        return value

    def validate_preauth_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "A threshold cannot be negative. Use 0 for no authorisation."
            )
        return value


class HmoEnrollmentSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    effective_coverage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    is_valid = serializers.BooleanField(read_only=True)
    # What the counter needs before dispensing: how much of the year's cover
    # this member still has. Null on an uncapped plan.
    remaining_benefit = serializers.SerializerMethodField()

    class Meta:
        model = HmoEnrollment
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def get_remaining_benefit(self, obj):
        return obj.remaining_benefit()

    def validate_coverage_percent(self, value):
        if value is not None and not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value

    def validate_annual_limit(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(
                "An annual limit cannot be negative. Leave it blank for no cap."
            )
        return value


class ClaimSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    sale_reference = serializers.CharField(source="sale.reference", read_only=True)
    patient_name = serializers.CharField(source="sale.patient.full_name",
                                         read_only=True)
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2,
                                           read_only=True)
    # The card the patient presented - the raw enrollment id says nothing to
    # anyone reading the claims table.
    enrollment_member_number = serializers.CharField(
        source="enrollment.member_number", read_only=True
    )
    # Which monthly schedule the claim sits on, if any — since a submitted
    # claim can still be collected, "is this on a schedule?" is a real question.
    batch_reference = serializers.CharField(source="batch.reference",
                                            read_only=True, allow_null=True)
    # The insurer's own clearance for the sale, when they asked for one — they
    # quote it back on the remittance.
    authorization_code = serializers.SerializerMethodField()

    def get_authorization_code(self, obj):
        auth = obj.sale.authorization
        return auth.code if auth else ""

    class Meta:
        model = Claim
        exclude = ("tenant",)
        # A claim is raised from a sale, never typed in: the amount is the
        # insurer's share of what was actually dispensed.
        read_only_fields = ("sale", "hmo", "enrollment", "reference", "amount",
                            "amount_approved", "amount_paid", "status",
                            "submitted_at", "settled_at", "rejection_reason",
                            "created_at", "updated_at")


class ClaimDecisionSerializer(serializers.Serializer):
    """The insurer's answer: an approved amount, or a reason for refusing."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      required=False, allow_null=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True,
                                   default="")


class ClaimPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      min_value=Decimal("0.01"))


class ClaimBatchSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    totals = serializers.DictField(read_only=True)

    class Meta:
        model = ClaimBatch
        exclude = ("tenant",)
        read_only_fields = ("reference", "status", "submitted_at", "created_at",
                            "updated_at")


class AddClaimsSerializer(serializers.Serializer):
    """Which claims to bundle. Left empty, the batch collects every unbatched
    open claim for its insurer inside its period."""

    claims = serializers.PrimaryKeyRelatedField(
        queryset=Claim.objects, many=True, required=False
    )


class HmoItemRuleSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    # What the pharmacy charges today, so a tariff is set against a real price
    # rather than from memory.
    item_price = serializers.DecimalField(
        source="item.unit_price", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = HmoItemRule
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value

    def validate_tariff(self, value):
        if value is not None and value < Decimal("0"):
            raise serializers.ValidationError("A tariff cannot be negative.")
        return value

    def validate_hmo(self, value):
        # An insurer keeps its own price list and nobody else's. The view
        # already refuses an edit to another scheme's row; this refuses a new
        # row filed under someone else's scheme, which has no row yet to check.
        user = self.context["request"].user
        if user.is_authenticated and user.role in INSURER_ROLES:
            if value.pk != user.hmo_id:
                raise serializers.ValidationError(
                    "You can only price your own scheme's list."
                )
        return value


class PreAuthorizationItemSerializer(serializers.ModelSerializer):
    """One ordered medication on a request, and the insurer's answer to it."""

    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = PreAuthorizationItem
        exclude = ("tenant", "authorization")
        # The insurer decides; the pharmacy only asks.
        read_only_fields = ("amount_approved", "quantity_approved", "status",
                            "reason", "decided_at", "created_at", "updated_at")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Ask the insurer for a positive amount.")
        return value


class PreAuthItemDecisionSerializer(serializers.Serializer):
    """The insurer's answer to one medication: an amount, or why it is refused."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      required=False, allow_null=True)
    # An insurer clearing 20 of the 30 tablets asked for. Blank stands behind
    # the whole quantity.
    quantity = serializers.IntegerField(min_value=1, required=False,
                                        allow_null=True)
    reason = serializers.CharField(max_length=255, required=False,
                                   allow_blank=True, default="")


class PreAuthorizationSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    patient_name = serializers.CharField(source="enrollment.patient.full_name",
                                         read_only=True)
    member_number = serializers.CharField(source="enrollment.member_number",
                                          read_only=True)
    is_usable = serializers.BooleanField(read_only=True)
    sale_reference = serializers.CharField(source="sale.reference",
                                           read_only=True, default="")
    # The ordered medications the insurer is being asked about. Optional: a
    # request may still be one lump sum for a basket.
    items = PreAuthorizationItemSerializer(many=True, required=False)

    class Meta:
        model = PreAuthorization
        exclude = ("tenant",)
        # The insurer decides everything but the ask: what the pharmacy sends is
        # a member and an amount, and the answer arrives through approve/decline.
        read_only_fields = ("reference", "hmo", "amount_approved", "code",
                            "status", "decided_at", "reason", "reopened_count",
                            "created_at", "updated_at")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Ask the insurer for a positive amount.")
        return value

    def create(self, validated_data):
        """An itemised request is worth what its medications add up to."""
        lines = validated_data.pop("items", [])
        if lines:
            validated_data["amount"] = sum(line["amount"] for line in lines)
        auth = super().create(validated_data)
        for line in lines:
            PreAuthorizationItem.objects.create(
                authorization=auth, tenant=auth.tenant, **line)
        return auth

    def validate_enrollment(self, value):
        if not value.is_valid:
            raise serializers.ValidationError(
                "That membership is inactive or out of date."
            )
        return value


class PreAuthDecisionSerializer(serializers.Serializer):
    """The insurer's answer: a code and what they will stand behind, or a
    reason for refusing."""

    code = serializers.CharField(max_length=60, required=False, allow_blank=True,
                                 default="")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2,
                                      required=False, allow_null=True)
    expires_on = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=255, required=False,
                                   allow_blank=True, default="")
