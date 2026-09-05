from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import normalize_phone
from apps.analytics.nigeria import valid_regions
from config.serializers import NamedRelationsMixin

from .models import Patient, PatientAccessLog


class PatientSerializer(NamedRelationsMixin, serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    age_group = serializers.CharField(read_only=True)
    patient_type_display = serializers.CharField(
        source="get_patient_type_display", read_only=True
    )
    is_nhia = serializers.BooleanField(read_only=True)
    merged_into_number = serializers.CharField(
        source="merged_into.hospital_number", read_only=True, default=""
    )
    registered_by_name = serializers.CharField(
        source="registered_by.username", read_only=True
    )
    chronic_condition_names = serializers.StringRelatedField(
        source="chronic_conditions", many=True, read_only=True
    )
    # Opt-out for the same-person check below. Not a model field — popped in
    # validate() so it never reaches the row.
    allow_duplicate = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Patient
        exclude = ("tenant",)
        # merged_into is set by the merge action only — never written directly.
        read_only_fields = ("registered_by", "consent_at", "merged_into",
                            "created_at", "updated_at")
        extra_kwargs = {
            # Blank means "generate one" (see Patient.save), so don't demand it.
            "hospital_number": {"required": False},
        }

    PHONE_FIELDS = ("phone", "next_of_kin_phone")

    def to_internal_value(self, data):
        """Fold phone numbers to one shape before anything else looks at them.

        Has to happen here, not in ``validate_phone``: field validators run
        first, and the Nigerian-number regex would reject "+234 803 123 4567"
        for its spaces before normalisation ever got a turn. Storing one shape
        is what makes ``?search=`` by phone and duplicate-spotting work.
        """
        if hasattr(data, "copy"):
            data = data.copy()
            for field in self.PHONE_FIELDS:
                if isinstance(data.get(field), str):
                    data[field] = normalize_phone(data[field])
        return super().to_internal_value(data)

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

    def _current(self, attrs, field):
        """Value after this write — the submitted one, else what's on file.

        Needed because a PATCH may change either half of a cross-field rule
        while the other half stays on the instance.
        """
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field, None)

    def _duplicate(self, attrs):
        """A patient already on file with the same names and date of birth.

        Name alone is far too common to act on, so the check needs a date of
        birth on both sides; without one the registration goes through.
        """
        dob = self._current(attrs, "date_of_birth")
        if not dob:
            return None
        rows = Patient.objects.filter(
            first_name__iexact=(self._current(attrs, "first_name") or "").strip(),
            last_name__iexact=(self._current(attrs, "last_name") or "").strip(),
            date_of_birth=dob,
        )
        if self.instance is not None:
            rows = rows.exclude(pk=self.instance.pk)
        return rows.first()

    def validate(self, attrs):
        allow_duplicate = attrs.pop("allow_duplicate", False)
        today = timezone.localdate()
        dob = attrs.get("date_of_birth")
        if dob and dob > today:
            raise serializers.ValidationError(
                {"date_of_birth": "Date of birth cannot be in the future."}
            )
        dod = self._current(attrs, "date_of_death")
        if dod:
            if dod > today:
                raise serializers.ValidationError(
                    {"date_of_death": "Date of death cannot be in the future."}
                )
            birth = self._current(attrs, "date_of_birth")
            if birth and dod < birth:
                raise serializers.ValidationError(
                    {"date_of_death": "Date of death is before the date of birth."}
                )
        # "merged" describes a record the merge action absorbed, and it hides
        # the row from lists — not something to be set by hand.
        if (self._current(attrs, "status") == Patient.Status.MERGED
                and self._current(attrs, "merged_into") is None):
            raise serializers.ValidationError(
                {"status": "Set by the merge action, not by hand."}
            )
        if not allow_duplicate:
            twin = self._duplicate(attrs)
            if twin is not None:
                raise serializers.ValidationError(
                    {"allow_duplicate": [
                        f"{twin.full_name} with this date of birth is already "
                        f"registered as {twin.hospital_number}. Send "
                        f"allow_duplicate=true to register them anyway."
                    ]}
                )
        # An NHIA patient is only NHIA if the scheme can be billed — the
        # enrolment number is what makes the exemption claimable.
        if self._current(attrs, "patient_type") == Patient.PatientType.NHIA:
            if not (self._current(attrs, "nhis_number") or "").strip():
                raise serializers.ValidationError(
                    {"nhis_number": "Required for NHIA patients."}
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
