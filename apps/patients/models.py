"""Patient registry — the one place in the platform that holds identifying data.

Everything else (case reports, lab results, immunizations, ...) stays
de-identified: those rows carry an age band and sex so they can be pooled
centrally, and only an optional FK back to here. A patient row never leaves its
tenant — the manager is tenant-scoped like the rest of the platform, and the
API gates reads to clinical staff (see apps.accounts.permissions).
"""
import secrets

from django.db import models, transaction

from apps.accounts.models import normalize_phone, phone_validator
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

    ``hospital_number`` is the facility's identifier for the patient and is
    unique per tenant. When the client doesn't supply one it is their own
    phone number, falling back to a generated number when there is no phone
    or the number is already another patient's here. A number that came from
    the phone follows it when the phone is corrected (see save).
    """

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"
        DECEASED = "deceased"
        # Not a person's state — a record's. Set by merge_from on the duplicate
        # that was absorbed; the row stays so its hospital number still resolves.
        MERGED = "merged"

    class PatientType(models.TextChoices):
        """How this patient's care is paid for — the billing route.

        Kept as one flat field rather than a table: the list is fixed by
        national scheme and facility policy, not by tenant.
        """

        REGULAR = "regular", "Regular"
        NHIA = "nhia", "NHIA"
        PRIVATE = "private", "Private Pay"
        INSURANCE = "insurance", "Private Insurance"
        CORPORATE = "corporate", "Corporate"
        STAFF = "staff", "Staff"
        DEPENDANT = "dependant", "Dependant"
        EMERGENCY = "emergency", "Emergency"
        RETAINERSHIP = "retainership", "Retainership"

    # Leading digit of a generated hospital number, by patient type: the first
    # digit tells records which billing route a patient is on without a lookup.
    # Types not listed fall back to DEFAULT_NUMBER_PREFIX.
    NUMBER_PREFIXES = {PatientType.NHIA: "4", PatientType.RETAINERSHIP: "3"}
    DEFAULT_NUMBER_PREFIX = "0"

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
    patient_type = models.CharField(
        max_length=15, choices=PatientType.choices, default=PatientType.REGULAR
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Set means the patient is dead: it freezes `age` and forces the status
    # (see save). A deceased patient with no known date keeps this null.
    date_of_death = models.DateField(null=True, blank=True)
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

    # Set on the duplicate when two records turn out to be one person.
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="merged_from",
    )
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
            models.Index(fields=["tenant", "patient_type"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.hospital_number})"

    @property
    def full_name(self):
        parts = [self.first_name, self.other_names, self.last_name]
        return " ".join(p for p in parts if p)

    @property
    def age(self):
        """Age in whole years, or None when no date of birth is on file.

        Counted to the date of death when there is one — a dead patient does
        not keep getting older, and their age band anchors every report they
        are linked to.
        """
        if not self.date_of_birth:
            return None
        from django.utils import timezone

        on = self.date_of_death or timezone.localdate()
        dob = self.date_of_birth
        return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))

    @property
    def age_group(self):
        return age_band(self.age)

    @property
    def is_nhia(self):
        """On the national insurance scheme — drives exemption at billing."""
        return self.patient_type == self.PatientType.NHIA

    def hospital_number_from_phone(self):
        """The patient's own phone as their hospital number, when it is free.

        A number is one person's, so it makes the identifier reception already
        has on the card. Returns "" when there is no phone, or when this
        tenant already gave that number to someone else (a shared family line,
        a recycled number) — the caller falls back to a generated number.
        """
        phone = normalize_phone(self.phone)
        if not phone:
            return ""
        taken = Patient.all_objects.filter(
            tenant_id=self.tenant_id, hospital_number=phone
        ).exclude(pk=self.pk)
        return "" if taken.exists() else phone

    # The phone this row was loaded with, so save() can tell a number that
    # followed the phone from one typed in by hand. None on an unsaved row.
    _db_phone = None

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        if "phone" in field_names:  # not set when the field was deferred
            obj._db_phone = values[field_names.index("phone")]
        return obj

    def generate_hospital_number(self):
        """A free 10-digit number whose leading digit encodes the patient type.

        Checked for collisions across all tenants, not just this one: the
        uniqueness constraint is per-tenant, but a globally free number
        satisfies it and needs no tenant bound at generation time.
        """
        prefix = self.NUMBER_PREFIXES.get(self.patient_type,
                                          self.DEFAULT_NUMBER_PREFIX)
        for _ in range(10):
            candidate = f"{prefix}{secrets.randbelow(10 ** 9):09d}"
            if not Patient.all_objects.filter(hospital_number=candidate).exists():
                return candidate
        # ponytail: 10 tries over a 1e9 space — losing all ten means the space
        # is full, not unlucky. Widen the number before adding retries.
        raise ValueError("Could not generate a free hospital number")

    # Reverse relations that must NOT follow a merge: the audit trail belongs to
    # the record that was read, and the tombstone chain is what merging builds.
    KEEP_ON_MERGE = ("access_log", "merged_from")

    def _clinical_relations(self):
        """Reverse FKs holding this patient's clinical records, audit aside."""
        return [
            rel for rel in self._meta.related_objects
            if rel.one_to_many and rel.get_accessor_name() not in self.KEEP_ON_MERGE
        ]

    def clinical_record_counts(self):
        """{relation name: row count} for everything filed against this patient."""
        counts = {}
        for rel in self._clinical_relations():
            n = rel.related_model._base_manager.filter(**{rel.field.name: self}).count()
            if n:
                counts[rel.get_accessor_name()] = n
        return counts

    def merge_from(self, source):
        """Absorb a duplicate record into this one. Returns {relation: rows moved}.

        Clinical rows are repointed here, fields still blank here are filled
        from the duplicate, and the duplicate is kept as a tombstone (status
        MERGED, ``merged_into`` set) rather than deleted — its hospital number
        is on paper somewhere and still has to resolve to the surviving record.
        """
        if source.pk == self.pk:
            raise ValueError("A patient cannot be merged into itself")
        # Fields the surviving record keeps whatever the duplicate says: its own
        # identity, its own record state, its own audit stamps.
        keep = {"id", "tenant", "hospital_number", "status", "merged_into",
                "created_at", "updated_at"}
        moved = {}
        with transaction.atomic():
            for rel in self._clinical_relations():
                rows = rel.related_model._base_manager.filter(
                    **{rel.field.name: source}
                )
                count = rows.update(**{rel.field.name: self})
                if count:
                    moved[rel.get_accessor_name()] = count
            for field in self._meta.concrete_fields:
                if field.name in keep:
                    continue
                if not getattr(self, field.name) and getattr(source, field.name):
                    setattr(self, field.name, getattr(source, field.name))
            self.chronic_conditions.add(*source.chronic_conditions.all())
            self.save()
            source.status = self.Status.MERGED
            source.merged_into = self
            source.save(update_fields=["status", "merged_into", "updated_at"])
        return moved

    def _also_save(self, kwargs, field):
        """Add ``field`` to an update_fields save that didn't ask for it."""
        fields = kwargs.get("update_fields")
        if fields is not None and field not in fields:
            kwargs["update_fields"] = list(fields) + [field]

    def save(self, *args, **kwargs):
        if not self.hospital_number:
            self.hospital_number = (self.hospital_number_from_phone()
                                    or self.generate_hospital_number())
        elif self.hospital_number == normalize_phone(self._db_phone or ""):
            # The number is the phone this row was loaded with, and the phone
            # has since changed: move the number with it. A new number that is
            # blank or already another patient's here leaves the old one alone
            # — a number that resolves beats one that matches the phone.
            moved = self.hospital_number_from_phone()
            if moved and moved != self.hospital_number:
                self.hospital_number = moved
                self._also_save(kwargs, "hospital_number")
        # A date of death outranks whatever status was sent: it is the harder
        # fact of the two. Bringing a patient back means clearing the date.
        # MERGED is exempt — that one describes the record, not the person.
        if self.date_of_death and self.status not in (self.Status.DECEASED,
                                                      self.Status.MERGED):
            self.status = self.Status.DECEASED
            self._also_save(kwargs, "status")
        super().save(*args, **kwargs)
        self._db_phone = self.phone


class PatientAccessLog(TenantOwnedModel):
    """Append-only record of who read — or erased — identifying patient data.

    Writes are already reconstructible (``registered_by``, ``updated_at``);
    reads leave no other trace, and "who looked at this record" is exactly what
    a data-protection regulator asks. A delete leaves even less: the row is
    gone, so the log entry is the only thing left saying it existed. One row per
    read/delete through the API — the Django admin is not covered.
    """

    class Action(models.TextChoices):
        LIST = "list"
        RETRIEVE = "retrieve"
        HISTORY = "history"
        DELETE = "delete"
        MERGE = "merge"

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
