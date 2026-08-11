"""Patient registry — the one place in the platform that holds identifying data.

Everything else (case reports, lab results, immunizations, ...) stays
de-identified: those rows carry an age band and sex so they can be pooled
centrally, and only an optional FK back to here. A patient row never leaves its
tenant — the manager is tenant-scoped like the rest of the platform, and the
API gates reads to clinical staff (see apps.accounts.permissions).
"""
import uuid

from django.db import models

from apps.accounts.models import phone_validator
from apps.tenants.models import TenantOwnedModel

# Age bands used across the analytics rollups, as (exclusive upper bound in
# years, label). First band the age falls under wins — "0-1" is infants only,
# so it has to be checked before "0-5". Kept in sync with simulate's AGES.
AGE_BANDS = [(1, "0-1"), (6, "0-5"), (13, "6-12"), (19, "13-18"),
             (41, "19-40"), (61, "41-60")]
AGE_BAND_OVER = "60+"


def age_band(years):
    """Analytics age band for an age in years, or "" when age is unknown."""
    if years is None:
        return ""
    for upper, label in AGE_BANDS:
        if years < upper:
            return label
    return AGE_BAND_OVER


class Patient(TenantOwnedModel):
    """A person registered at one facility (tenant).

    ``hospital_number`` is the facility's own identifier and is unique per
    tenant; it is generated when the client doesn't supply one so registration
    never blocks on a numbering scheme.
    """

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"
        DECEASED = "deceased"

    class BloodGroup(models.TextChoices):
        A_POS = "A+"
        A_NEG = "A-"
        B_POS = "B+"
        B_NEG = "B-"
        AB_POS = "AB+"
        AB_NEG = "AB-"
        O_POS = "O+"
        O_NEG = "O-"

    class Genotype(models.TextChoices):
        AA = "AA"
        AS = "AS"
        AC = "AC"
        SS = "SS"
        SC = "SC"

    hospital_number = models.CharField(max_length=50, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(
        max_length=20, blank=True, validators=[phone_validator]
    )
    address = models.TextField(blank=True)
    region = models.CharField(max_length=120, blank=True)  # "LGA, State"

    blood_group = models.CharField(
        max_length=5, choices=BloodGroup.choices, blank=True
    )
    genotype = models.CharField(max_length=5, choices=Genotype.choices, blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.ManyToManyField(
        "catalog.Disease", blank=True, related_name="patients"
    )

    nhis_number = models.CharField(max_length=50, blank=True)
    next_of_kin_name = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True)
    next_of_kin_relationship = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    # Consent to store and process identifying data. Recorded, not enforced —
    # the facility owns the legal basis; this is the audit trail for it.
    consent_given = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)

    registered_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="registered_patients",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("last_name", "first_name", "id")
        unique_together = ("tenant", "hospital_number")
        indexes = [
            models.Index(fields=["tenant", "last_name"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "phone"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.hospital_number})"

    @property
    def full_name(self):
        parts = [self.first_name, self.other_names, self.last_name]
        return " ".join(p for p in parts if p)

    @property
    def age(self):
        """Age in whole years, or None when no date of birth is on file."""
        if not self.date_of_birth:
            return None
        from django.utils import timezone

        today = timezone.localdate()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def age_group(self):
        return age_band(self.age)

    def save(self, *args, **kwargs):
        if not self.hospital_number:
            # ponytail: random suffix, not a per-tenant counter — no SELECT MAX
            # race to lose. Swap for a sequence only if facilities need
            # gap-free numbering.
            self.hospital_number = f"P-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class PatientAccessLog(TenantOwnedModel):
    """Append-only record of who read identifying patient data.

    Writes are already reconstructible (``registered_by``, ``updated_at``);
    reads leave no other trace, and "who looked at this record" is exactly what
    a data-protection regulator asks. One row per read through the API — the
    Django admin is not covered.
    """

    class Action(models.TextChoices):
        LIST = "list"
        RETRIEVE = "retrieve"
        HISTORY = "history"

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="patient_accesses",
    )
    # SET_NULL, not CASCADE: deleting a patient must not erase the trail of who
    # read them. Always null for a list read, which spans many patients.
    patient = models.ForeignKey(
        Patient, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="access_log",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    query = models.CharField(max_length=255, blank=True)  # the ?search= used
    result_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["patient", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.action} patient {self.patient_id}"
