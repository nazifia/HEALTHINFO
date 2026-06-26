from rest_framework import serializers

from .models import (
    Article,
    Disease,
    DrugInteraction,
    LabTest,
    Medication,
    Procedure,
    Specialty,
    Symptom,
)


class SymptomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symptom
        exclude = ("tenant",)


class DiseaseSerializer(serializers.ModelSerializer):
    # M2M PK lists. The related managers are tenant-scoped, so DRF will reject
    # any symptom/medication id that belongs to another tenant.
    class Meta:
        model = Disease
        exclude = ("tenant",)  # tenant set server-side, never client-supplied


class MedicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Medication
        exclude = ("tenant",)


class DrugInteractionSerializer(serializers.ModelSerializer):
    # Read-only display names so clients render the pair without N extra GETs.
    medication_a_name = serializers.CharField(
        source="medication_a.generic_name", read_only=True
    )
    medication_b_name = serializers.CharField(
        source="medication_b.generic_name", read_only=True
    )

    class Meta:
        model = DrugInteraction
        exclude = ("tenant",)


class SpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialty
        exclude = ("tenant",)


class ProcedureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Procedure
        exclude = ("tenant",)


class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        exclude = ("tenant",)


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        exclude = ("tenant",)
