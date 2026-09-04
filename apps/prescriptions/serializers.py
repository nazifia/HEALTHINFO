from decimal import Decimal

from rest_framework import serializers

from .models import (
    ConsultationPayout,
    Hospital,
    Prescriber,
    Prescription,
    PrescriberCommission,
    PrescriptionItem,
)


class HospitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hospital
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")


class PrescriberSerializer(serializers.ModelSerializer):
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)
    consultation_fees = serializers.DictField(read_only=True)
    outstanding = serializers.DictField(read_only=True)

    class Meta:
        model = Prescriber
        exclude = ("tenant",)
        read_only_fields = ("created_at", "updated_at")

    def validate_commission_rate(self, value):
        if not Decimal("0") <= value <= Decimal("100"):
            raise serializers.ValidationError("Commission must be between 0 and 100.")
        return value


class PrescriptionItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = PrescriptionItem
        exclude = ("tenant", "prescription")
        # Dispensing is an event, not a field: it goes through the line's
        # ``dispense`` action so the script's status follows it.
        read_only_fields = ("is_dispensed", "dispensed_at", "dispensed_by",
                            "created_at", "updated_at")


class PrescriptionSerializer(serializers.ModelSerializer):
    lines = PrescriptionItemSerializer(many=True, read_only=True)
    medications = PrescriptionItemSerializer(many=True, write_only=True,
                                             required=False)
    prescriber_name = serializers.CharField(source="prescriber.name", read_only=True)
    prescriber_license = serializers.CharField(source="prescriber.license_number",
                                               read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.username",
                                            read_only=True)

    class Meta:
        model = Prescription
        exclude = ("tenant",)
        # Status follows the lines; the consultation fee is snapshotted from
        # the prescriber's band when the script is written up.
        read_only_fields = ("status", "consultation_fee", "dispensed_at",
                            "created_by", "created_at", "updated_at")

    def validate_consultation_category(self, value):
        letter = (value or "").strip().upper()
        if letter and letter not in Prescriber.CONSULT_CATEGORIES:
            raise serializers.ValidationError(
                f"Category must be one of {', '.join(Prescriber.CONSULT_CATEGORIES)}."
            )
        return letter

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


class PrescriberCommissionSerializer(serializers.ModelSerializer):
    prescriber_name = serializers.CharField(source="prescriber.name", read_only=True)

    class Meta:
        model = PrescriberCommission
        exclude = ("tenant",)
        read_only_fields = ("prescriber", "prescription", "sale", "patient_name",
                            "sales_amount", "commission_rate", "commission_amount",
                            "status", "paid_at", "created_at", "updated_at")


class ConsultationPayoutSerializer(serializers.ModelSerializer):
    prescriber_name = serializers.CharField(source="prescriber.name", read_only=True)

    class Meta:
        model = ConsultationPayout
        exclude = ("tenant",)
        read_only_fields = ("prescriber", "prescription", "patient_name",
                            "consultation_category", "consultation_fee", "status",
                            "paid_at", "created_at", "updated_at")
