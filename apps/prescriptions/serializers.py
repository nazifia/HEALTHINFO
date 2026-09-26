from rest_framework import serializers

from apps.analytics.models import Prescription as DrugOrder
from config.serializers import NamedRelationsMixin

from .models import Prescription, PrescriptionItem


class PrescriptionItemSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = PrescriptionItem
        exclude = ("tenant", "prescription")
        # Dispensing is an event, not a field: it goes through the line's
        # ``dispense`` action so the script's status follows it.
        read_only_fields = ("is_dispensed", "dispensed_at", "dispensed_by",
                            "created_at", "updated_at")


class PrescriptionSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    lines = PrescriptionItemSerializer(many=True, read_only=True)
    medications = PrescriptionItemSerializer(many=True, write_only=True,
                                             required=False)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username",
                                            read_only=True)

    class Meta:
        model = Prescription
        exclude = ("tenant",)
        # Status follows the lines.
        read_only_fields = ("status", "dispensed_at",
                            "created_by", "created_at", "updated_at")

    def create(self, validated_data):
        lines = validated_data.pop("medications", [])
        rx = Prescription(**validated_data)
        rx.save()
        for line in lines:
            PrescriptionItem.all_objects.create(
                tenant=rx.tenant, prescription=rx, **line
            )
        return rx

    def update(self, instance, validated_data):
        """Lines are replaced wholesale, and only before anything went out.

        Once a drug has been handed over, the script is a record of what was
        dispensed; editing it would make the dispensing log describe something
        that was never written.
        """
        lines = validated_data.pop("medications", None)
        if lines is not None:
            if instance.status != Prescription.Status.PENDING:
                raise serializers.ValidationError(
                    {"medications": "This script has already been part-dispensed."}
                )
            PrescriptionItem.all_objects.filter(prescription=instance).delete()
            for line in lines:
                PrescriptionItem.all_objects.create(
                    tenant=instance.tenant, prescription=instance, **line
                )
        return super().update(instance, validated_data)


class OutsideOrderSerializer(serializers.ModelSerializer):
    """A drug order as a pharmacy outside the writing facility may read it.

    A patient hands a pharmacy their number, not their file, so this carries
    the prescription and nothing else: the drug, the directions, where it was
    written and by whom. No name, no age band, no diagnosis, no notes — the
    patient record stays inside the facility that holds it, which is the rule
    everything else in the platform keeps too.
    """

    medication_name = serializers.CharField(source="medication.generic_name",
                                            read_only=True)
    prescriber_name = serializers.CharField(source="prescriber", read_only=True)
    facility = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = DrugOrder
        fields = ("id", "medication", "medication_name", "dose", "frequency",
                  "duration_days", "status", "group", "prescriber_name",
                  "facility", "created_at")
        read_only_fields = fields


class OutsideScriptLineSerializer(serializers.ModelSerializer):
    """A line of another pharmacy's script: the drug and directions, not the
    stock item — that id belongs to the shelf it was written up against."""

    class Meta:
        model = PrescriptionItem
        fields = ("id", "name", "brand", "quantity", "unit", "dosage", "duration",
                  "instructions", "is_dispensed")
        read_only_fields = fields


class OutsideScriptSerializer(serializers.ModelSerializer):
    """A counter script as a pharmacy other than the one that wrote it up
    may read it: what was prescribed, by whom and where — and, like
    OutsideOrderSerializer, nothing about the patient."""

    # Through the model's own lookup, not the related manager: that reads
    # through the tenant-scoped manager and this reader is another tenant.
    lines = OutsideScriptLineSerializer(many=True, read_only=True, source="_lines")
    facility = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = Prescription
        fields = ("id", "lines", "status", "doctor_name", "facility",
                  "created_at")
        read_only_fields = fields
