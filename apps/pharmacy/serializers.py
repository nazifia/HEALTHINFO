from decimal import Decimal

from rest_framework import serializers

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    HmoItemRule,
    PreAuthorization,
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

    class Meta:
        model = HmoItemRule
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value


class PreAuthorizationSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    patient_name = serializers.CharField(source="enrollment.patient.full_name",
                                         read_only=True)
    member_number = serializers.CharField(source="enrollment.member_number",
                                          read_only=True)
    is_usable = serializers.BooleanField(read_only=True)
    sale_reference = serializers.CharField(source="sale.reference",
                                           read_only=True, default="")

    class Meta:
        model = PreAuthorization
        exclude = ("tenant",)
        # The insurer decides everything but the ask: what the pharmacy sends is
        # a member and an amount, and the answer arrives through approve/decline.
        read_only_fields = ("reference", "hmo", "amount_approved", "code",
                            "status", "decided_at", "reason", "created_at",
                            "updated_at")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Ask the insurer for a positive amount.")
        return value

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
