from django.utils import timezone
from rest_framework import serializers

from apps.analytics.nigeria import valid_regions

from .models import Patient, PatientAccessLog


class PatientSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    age_group = serializers.CharField(read_only=True)
    registered_by_name = serializers.CharField(
        source="registered_by.username", read_only=True
    )
    chronic_condition_names = serializers.StringRelatedField(
        source="chronic_conditions", many=True, read_only=True
    )

    class Meta:
        model = Patient
        exclude = ("tenant",)
        read_only_fields = ("registered_by", "consent_at", "created_at", "updated_at")
        extra_kwargs = {
            # Blank means "generate one" (see Patient.save), so don't demand it.
            "hospital_number": {"required": False},
        }

    def validate_region(self, value):
        if value and value not in valid_regions():
            raise serializers.ValidationError(
                "Not a valid Nigerian LGA, State. Pick from the list."
            )
        return value

    def validate_hospital_number(self, value):
        # unique_together (tenant, hospital_number) can't be checked by DRF's
        # UniqueTogetherValidator here — tenant is excluded from the serializer
        # and stamped server-side — so check it against the tenant-scoped
        # manager, which only ever sees this tenant's rows.
        value = (value or "").strip()
        if not value:
            return value
        clash = Patient.objects.filter(hospital_number=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                "A patient with this hospital number already exists."
            )
        return value

    def validate(self, attrs):
        dob = attrs.get("date_of_birth")
        if dob and dob > timezone.localdate():
            raise serializers.ValidationError(
                {"date_of_birth": "Date of birth cannot be in the future."}
            )
        return attrs

    def _stamp_consent(self, validated_data, instance=None):
        """Record when consent was first given; clear it when withdrawn."""
        if "consent_given" not in validated_data:
            return
        given = validated_data["consent_given"]
        was = getattr(instance, "consent_given", False)
        if given and not was:
            validated_data["consent_at"] = timezone.now()
        elif not given:
            validated_data["consent_at"] = None

    def create(self, validated_data):
        self._stamp_consent(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._stamp_consent(validated_data, instance)
        return super().update(instance, validated_data)


class PatientAccessLogSerializer(serializers.ModelSerializer):
    """Read-only view of the access trail. Never written through the API —
    rows are stamped by the viewset on each read."""

    user_name = serializers.CharField(source="user.username", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)

    class Meta:
        model = PatientAccessLog
        exclude = ("tenant",)
        read_only_fields = [f.name for f in PatientAccessLog._meta.fields]
