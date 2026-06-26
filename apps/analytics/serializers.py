from rest_framework import serializers

from .models import (
    AdverseDrugReaction,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    StockReport,
    VitalEvent,
)
from .nigeria import valid_regions


def _validate_region(value):
    # Optional. If supplied, must be a known "LGA, State" from the Nigeria list.
    if value and value not in valid_regions():
        raise serializers.ValidationError(
            "Not a valid Nigerian LGA, State. Pick from the list."
        )
    return value


class CaseReportSerializer(serializers.ModelSerializer):
    # reporter + tenant set server-side, never client-supplied. M2M managers are
    # tenant-scoped, so DRF rejects any symptom/medication/disease from another tenant.
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = CaseReport
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class AdverseDrugReactionSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    medication_name = serializers.CharField(
        source="medication.generic_name", read_only=True
    )

    class Meta:
        model = AdverseDrugReaction
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class LabResultSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    lab_test_name = serializers.CharField(source="lab_test.name", read_only=True)
    disease_name = serializers.CharField(source="disease.name", read_only=True)

    class Meta:
        model = LabResult
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class ImmunizationSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = Immunization
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class VitalEventSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    cause_name = serializers.CharField(source="cause.name", read_only=True)

    class Meta:
        model = VitalEvent
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class StockReportSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    medication_name = serializers.CharField(
        source="medication.generic_name", read_only=True
    )

    class Meta:
        model = StockReport
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class CommunityHealthReportSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = CommunityHealthReport
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class FacilityMetricSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    occupancy_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = FacilityMetric
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class InsuranceClaimSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    diagnosis_name = serializers.CharField(source="diagnosis.name", read_only=True)

    class Meta:
        model = InsuranceClaim
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class AppointmentSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = Appointment
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)
