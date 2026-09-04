from decimal import Decimal

from rest_framework import serializers

from .models import HMO, Claim, ClaimBatch, HmoEnrollment


class HMOSerializer(serializers.ModelSerializer):
    class Meta:
        model = HMO
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
        return value


class HmoEnrollmentSerializer(serializers.ModelSerializer):
    hmo_name = serializers.CharField(source="hmo.name", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    effective_coverage = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = HmoEnrollment
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_coverage_percent(self, value):
        if value is not None and not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Coverage must be between 0 and 100.")
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
