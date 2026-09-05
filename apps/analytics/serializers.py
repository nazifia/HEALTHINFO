from rest_framework import serializers

from config.serializers import NamedRelationsMixin

from .models import (
    AdverseDrugReaction,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    Consultation,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    Prescription,
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


class CaseReportSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    # reporter + tenant set server-side, never client-supplied. M2M managers are
    # tenant-scoped, so DRF rejects any symptom/medication/disease from another tenant.
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = CaseReport
        exclude = ("tenant",)
        # source_ref is provenance written by capture, never by a client.
        read_only_fields = ("reporter", "source_ref", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class AdverseDrugReactionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
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
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
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
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = Immunization
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class VitalEventSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
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
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
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
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    diagnosis_name = serializers.CharField(source="diagnosis.name", read_only=True)

    class Meta:
        model = InsuranceClaim
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)

    class Meta:
        model = Appointment
        exclude = ("tenant",)
        read_only_fields = ("reporter", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class PrescriptionSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    medication_name = serializers.CharField(
        source="medication.generic_name", read_only=True
    )

    class Meta:
        model = Prescription
        exclude = ("tenant",)
        # source_ref is provenance written by capture, never by a client.
        read_only_fields = ("reporter", "source_ref", "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)


class ConsultationSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    reporter_name = serializers.CharField(source="reporter.username", read_only=True)
    # The diagnosis this visit reached. It lives on the case report — this is a
    # label so a client can show it without fetching the case per row.
    case_report_disease = serializers.CharField(
        source="case_report.disease.name", read_only=True
    )
    # What the clinician actually wrote. A diagnosis the catalog has never heard
    # of matches no disease, so without this a client would show a visit with no
    # diagnosis at all where one was recorded in plain words.
    case_report_notes = serializers.CharField(
        source="case_report.notes", read_only=True
    )
    # Derived from the vitals on the row, never sent by a client.
    bmi = serializers.FloatField(read_only=True)
    blood_pressure = serializers.CharField(read_only=True)
    abnormal_vitals = serializers.ListField(child=serializers.CharField(),
                                            read_only=True)

    class Meta:
        model = Consultation
        exclude = ("tenant",)
        # A consultation is closed through the `close` action, which settles the
        # appointment and the case report with it. Letting a client PATCH these
        # straight would close the note and leave both of those behind.
        read_only_fields = ("reporter", "status", "disposition", "closed_at",
                            "created_at", "updated_at")

    def validate_region(self, value):
        return _validate_region(value)
