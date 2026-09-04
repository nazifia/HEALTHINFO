from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.tenants.models import TenantOwnedModel


class PatientLinkedModel(models.Model):
    """De-identified patient demographics, plus an optional link to a registered
    patient (apps.patients).

    The age band and sex columns stay the source of truth for every rollup, so
    central collation never has to touch the patient row and cross-tenant
    pooling stays PII-free. Linking a patient just fills them in — an explicit
    value the reporter typed always wins.
    """

    patient = models.ForeignKey(
        "patients.Patient", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )
    patient_age_group = models.CharField(max_length=20, blank=True)  # e.g. "0-5", "60+"
    patient_sex = models.CharField(max_length=10, blank=True)  # M/F/other, optional

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.patient_id:
            self.patient_age_group = self.patient_age_group or self.patient.age_group
            self.patient_sex = self.patient_sex or self.patient.sex
        super().save(*args, **kwargs)


class AnalyticsEvent(TenantOwnedModel):
    """One table for every tracked interaction. event_type discriminates
    searches (query set) from content views (object_type + object_id set)."""

    SEARCH = "search"
    VIEW = "view"

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    event_type = models.CharField(max_length=20)
    query = models.CharField(max_length=500, blank=True)
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    # Hits returned for a search. null = not a search / not recorded; 0 = content
    # gap (user searched, we had nothing). Drives the content-gaps report.
    result_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "event_type", "created_at"]),
            models.Index(fields=["tenant", "object_type", "object_id"]),
        ]


class CaseReport(PatientLinkedModel, TenantOwnedModel):
    """A case reported by tenant staff, linked to catalog content.

    Stored tenant-scoped like everything else; the platform (super-admin) view
    reads across tenants via ``all_objects`` to collate for analysis. Holds no
    patient PII — only aggregate demographics (age band, sex) so reports can be
    pooled centrally without identifying anyone.
    """

    class Severity(models.TextChoices):
        MILD = "mild"
        MODERATE = "moderate"
        SEVERE = "severe"
        CRITICAL = "critical"

    class Outcome(models.TextChoices):
        ONGOING = "ongoing"
        RECOVERED = "recovered"
        REFERRED = "referred"
        DECEASED = "deceased"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    disease = models.ForeignKey(
        "catalog.Disease", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="case_reports",
    )
    symptoms = models.ManyToManyField(
        "catalog.Symptom", blank=True, related_name="case_reports"
    )
    medications = models.ManyToManyField(
        "catalog.Medication", blank=True, related_name="case_reports"
    )
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MILD
    )
    outcome = models.CharField(
        max_length=20, choices=Outcome.choices, default=Outcome.ONGOING
    )
    # Coarse location (district/state). No street address — keeps reports
    # poolable centrally without identifying anyone. Drives hotspot maps.
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    # The counter row this was captured from ("rx:12"). NULL — not "" — when a
    # person filed the case by hand: NULLs never collide in a unique index on
    # any backend, so the constraint below can be plain rather than partial
    # (MySQL has no partial index). apps.analytics.capture keys on it so one
    # script filled over several visits stays one case.
    source_ref = models.CharField(
        max_length=100, null=True, blank=True, default=None
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "disease"]),
            models.Index(fields=["tenant", "region"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_ref"],
                name="analytics_case_one_row_per_source",
            ),
        ]

    def __str__(self):
        return f"Case #{self.pk} ({self.severity})"


class AiInteraction(TenantOwnedModel):
    """Full RAG Q&A kept for analysis: answer quality, hallucination audits,
    eval/training sets. answer is null when running retrieval-only (no API key)."""

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    UP = "up"
    DOWN = "down"

    question = models.TextField()
    answer = models.TextField(null=True, blank=True)
    sources = models.JSONField(default=list, blank=True)  # ranked hits w/ scores
    model_name = models.CharField(max_length=100, blank=True)
    feedback = models.CharField(
        max_length=4, blank=True,
        choices=[(UP, "thumbs up"), (DOWN, "thumbs down")],
    )

    class Meta:
        indexes = [models.Index(fields=["tenant", "created_at"])]


class AdverseDrugReaction(PatientLinkedModel, TenantOwnedModel):
    """Pharmacovigilance report: a suspected harm from a medication.

    Distinct from CaseReport (which is disease-centric) — the unit here is a
    drug + the reaction it's suspected of causing. Holds no PII, only aggregate
    demographics, so reports pool centrally like CaseReport.
    """

    class Severity(models.TextChoices):
        MILD = "mild"
        MODERATE = "moderate"
        SEVERE = "severe"
        LIFE_THREATENING = "life_threatening"

    class Outcome(models.TextChoices):
        ONGOING = "ongoing"
        RECOVERED = "recovered"
        RECOVERED_SEQUELAE = "recovered_with_sequelae"
        FATAL = "fatal"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    medication = models.ForeignKey(
        "catalog.Medication", on_delete=models.CASCADE, related_name="adverse_reactions"
    )
    reaction = models.CharField(max_length=255)  # e.g. "anaphylaxis", "rash"
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MILD
    )
    outcome = models.CharField(
        max_length=25, choices=Outcome.choices, default=Outcome.ONGOING
    )
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "medication"]),
        ]

    def __str__(self):
        return f"ADR #{self.pk} ({self.reaction})"


class LabResult(PatientLinkedModel, TenantOwnedModel):
    """A laboratory test result — lab-confirmed surveillance + the AMR signal.

    When organism + antibiotic + susceptibility are filled the row doubles as an
    antimicrobial-resistance data point (the lab cultured a bug and tested a drug
    against it). Holds no PII, only coarse demographics + region, so results pool
    centrally like CaseReport. Mirrors that model's reporting pattern.
    """

    class Flag(models.TextChoices):
        NORMAL = "normal"
        ABNORMAL = "abnormal"
        CRITICAL = "critical"

    class Susceptibility(models.TextChoices):
        SUSCEPTIBLE = "susceptible"
        INTERMEDIATE = "intermediate"
        RESISTANT = "resistant"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    lab_test = models.ForeignKey(
        "catalog.LabTest", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="results",
    )
    disease = models.ForeignKey(
        "catalog.Disease", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="lab_results",
    )
    value = models.CharField(max_length=255, blank=True)  # e.g. "12.3 g/dL"
    flag = models.CharField(max_length=20, choices=Flag.choices, default=Flag.NORMAL)
    organism = models.CharField(max_length=120, blank=True)  # culture isolate
    antibiotic = models.CharField(max_length=120, blank=True)  # drug tested (AST)
    susceptibility = models.CharField(
        max_length=20, choices=Susceptibility.choices, blank=True
    )
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "organism"]),
        ]

    def __str__(self):
        return f"Lab #{self.pk} ({self.organism or self.flag})"


class Immunization(PatientLinkedModel, TenantOwnedModel):
    """A vaccine dose administered — one row of the immunization registry.

    Coverage analysis groups by vaccine, region and age band. No PII; coarse
    demographics + region only, so doses pool centrally like CaseReport.
    """

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    vaccine = models.CharField(max_length=120)  # e.g. "BCG", "Measles", "OPV"
    dose_number = models.PositiveSmallIntegerField(default=1)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "vaccine"]),
        ]

    def __str__(self):
        return f"{self.vaccine} dose {self.dose_number}"


class VitalEvent(PatientLinkedModel, TenantOwnedModel):
    """A birth or death — vital registration. Both kinds live in one model so the
    platform can derive maternal & infant mortality (deaths over live births).

    ``maternal_death``/``infant_death`` flag the deaths that feed those ratios.
    No PII; coarse demographics + region only.
    """

    class Kind(models.TextChoices):
        BIRTH = "birth"
        DEATH = "death"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    event_type = models.CharField(max_length=10, choices=Kind.choices)
    cause = models.ForeignKey(
        "catalog.Disease", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="vital_events", help_text="Cause of death (deaths only).",
    )
    # Death related to pregnancy/childbirth — numerator of the maternal mortality ratio.
    maternal_death = models.BooleanField(default=False)
    # Death under 1 year — numerator of the infant mortality rate.
    infant_death = models.BooleanField(default=False)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "event_type", "created_at"]),
            models.Index(fields=["tenant", "region"]),
        ]

    def __str__(self):
        return f"{self.event_type} #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # A registered death closes the patient's record too — the registry and
        # vital registration must not disagree about who is alive. Only ever
        # fills a blank date; a date already on file was entered deliberately.
        if self.event_type == self.Kind.DEATH and self.patient_id:
            patient = self.patient
            if patient.status != patient.Status.DECEASED:
                patient.date_of_death = (
                    patient.date_of_death or timezone.localdate()
                )
                patient.status = patient.Status.DECEASED
                patient.save(update_fields=["date_of_death", "status", "updated_at"])


class StockReport(TenantOwnedModel):
    """Pharmacy stock & consumption snapshot for a medication.

    ``shortage`` flags a stock-out risk so central can spot and resupply gaps;
    ``consumed`` feeds medicine-usage trends (incl. antibiotic stewardship).
    """

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    medication = models.ForeignKey(
        "catalog.Medication", on_delete=models.CASCADE, related_name="stock_reports"
    )
    on_hand = models.PositiveIntegerField(default=0)  # units currently in stock
    consumed = models.PositiveIntegerField(default=0)  # units used this period
    shortage = models.BooleanField(default=False)  # stocked-out / below buffer
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "medication"]),
        ]

    def __str__(self):
        return f"Stock #{self.pk} ({self.medication_id}: {self.on_hand})"


class CommunityHealthReport(PatientLinkedModel, TenantOwnedModel):
    """A community health worker's field report — care happening outside a
    facility: antenatal visits, newborns, malnutrition screening, and deaths
    that occur at home. ``referred`` flags cases sent on to a facility.
    """

    class Kind(models.TextChoices):
        PREGNANCY = "pregnancy"
        NEWBORN = "newborn"
        MALNUTRITION = "malnutrition"
        DEATH = "death"  # death occurring outside a facility
        OTHER = "other"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    report_type = models.CharField(max_length=20, choices=Kind.choices)
    danger_signs = models.BooleanField(default=False)  # needs urgent attention
    referred = models.BooleanField(default=False)  # sent on to a facility
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "report_type", "created_at"]),
            models.Index(fields=["tenant", "region"]),
        ]

    def __str__(self):
        return f"CHW {self.report_type} #{self.pk}"


class FacilityMetric(TenantOwnedModel):
    """A facility's service-performance snapshot for one day — the KPIs central
    watches: bed occupancy, waiting time, staffing and throughput.

    Occupancy rate is derived (occupied / total beds), not stored, so it can't
    drift from its inputs.
    """

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    beds_total = models.PositiveIntegerField(default=0)
    beds_occupied = models.PositiveIntegerField(default=0)
    avg_wait_minutes = models.PositiveIntegerField(default=0)
    staff_on_duty = models.PositiveIntegerField(default=0)
    patients_treated = models.PositiveIntegerField(default=0)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["tenant", "created_at"])]

    @property
    def occupancy_rate(self):
        """Occupied / total beds (0..1), or None when no beds recorded."""
        return self.beds_occupied / self.beds_total if self.beds_total else None

    def __str__(self):
        return f"Metrics #{self.pk} ({self.patients_treated} treated)"


class InsuranceClaim(PatientLinkedModel, TenantOwnedModel):
    """A health-insurance claim — utilization + cost signal. Diagnosis links to
    the catalog so claims pool by ICD-10 like case reports. No PII.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
        PAID = "paid"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    diagnosis = models.ForeignKey(
        "catalog.Disease", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="claims",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED
    )
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["tenant", "diagnosis"]),
        ]

    def __str__(self):
        return f"Claim #{self.pk} ({self.status}: {self.amount})"


class Appointment(PatientLinkedModel, TenantOwnedModel):
    """A scheduled encounter — in-person or telemedicine. Feeds utilization and
    the no-show rate that signals access/adherence problems.
    """

    class Mode(models.TextChoices):
        IN_PERSON = "in_person"
        TELEMEDICINE = "telemedicine"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        COMPLETED = "completed"
        NO_SHOW = "no_show"
        CANCELLED = "cancelled"

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.IN_PERSON)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    reason = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "mode", "created_at"]),
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"Appt #{self.pk} ({self.mode}/{self.status})"


class Prescription(PatientLinkedModel, TenantOwnedModel):
    """A drug order: what was prescribed, how much, how often, how long, and
    whether the pharmacy dispensed it.

    ``CaseReport.medications`` records only *that* a drug was involved in a case;
    this is the order itself. ``case_report`` links back to the diagnosis it was
    written for, so a prescription is never orphaned from its reason.
    """

    class Status(models.TextChoices):
        PRESCRIBED = "prescribed"
        PARTIAL = "partially_dispensed"
        DISPENSED = "dispensed"
        CANCELLED = "cancelled"

    reporter = models.ForeignKey(  # the prescriber
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    case_report = models.ForeignKey(
        "analytics.CaseReport", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prescriptions",
    )
    medication = models.ForeignKey(
        "catalog.Medication", on_delete=models.CASCADE, related_name="prescriptions"
    )
    dose = models.CharField(max_length=120, blank=True)  # e.g. "500 mg"
    frequency = models.CharField(max_length=120, blank=True)  # e.g. "twice daily"
    duration_days = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.PRESCRIBED
    )
    dispensed_at = models.DateTimeField(null=True, blank=True)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    # The dispensing row this was captured from ("rxline:8", "dispense:44").
    # NULL when a clinician wrote the order here directly — see CaseReport for
    # why NULL and not "". apps.analytics.capture keys on it: one drug handed
    # over is one row, whichever route it came down, and the constraint below
    # makes that the database's rule rather than the capture code's.
    source_ref = models.CharField(
        max_length=100, null=True, blank=True, default=None
    )

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["tenant", "medication"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_ref"],
                name="analytics_rx_one_row_per_source",
            ),
        ]

    def __str__(self):
        return f"Rx #{self.pk} ({self.medication_id}: {self.status})"

    def save(self, *args, **kwargs):
        # Dispensing stamps its own time so the two can't disagree; a time
        # already on file was entered deliberately and stands.
        if self.status == self.Status.DISPENSED and not self.dispensed_at:
            self.dispensed_at = timezone.now()
        super().save(*args, **kwargs)


# Triage bands: field -> (low, high), both inclusive. Outside the band is
# flagged for a second look, never rejected — the field validators are what
# reject a typo, so `abnormal_vitals` is a prompt, not a finding.
TRIAGE_BANDS = {
    "temperature_c": (35.0, 37.9),
    "pulse_bpm": (60, 100),
    "respiratory_rate": (12, 20),
    "systolic_bp": (90, 139),
    "diastolic_bp": (60, 89),
    "oxygen_saturation": (94, 100),
}

# What those bands become for a child, keyed by the age band on the row (the
# labels apps.patients.age_band produces). Only the fields that actually move
# with age are overridden — a child's temperature and oxygen saturation are an
# adult's, and everything not listed falls back to the adult band above.
PAEDIATRIC_TRIAGE_BANDS = {
    "0-1": {
        "pulse_bpm": (100, 160),
        "respiratory_rate": (30, 60),
        "systolic_bp": (70, 100),
        "diastolic_bp": (35, 65),
    },
    "0-5": {  # 1-5: "0-1" is checked first, so this band never sees an infant
        "pulse_bpm": (90, 140),
        "respiratory_rate": (20, 40),
        "systolic_bp": (80, 110),
        "diastolic_bp": (40, 70),
    },
    "6-12": {
        "pulse_bpm": (70, 120),
        "respiratory_rate": (18, 30),
        "systolic_bp": (85, 120),
        "diastolic_bp": (45, 80),
    },
    "13-18": {
        "pulse_bpm": (60, 110),
        "respiratory_rate": (12, 24),
        "systolic_bp": (95, 135),
        "diastolic_bp": (55, 85),
    },
}


# A child's blood pressure tracks height more closely than age, so a measured
# height replaces the age band's cuff numbers. Straight-line fit through the
# percentile-table anchors (60cm: 70-100/35-65, 168cm: 95-135/55-85), which
# reproduces the intermediate rows to a couple of mmHg.
# ponytail: a linear fit, not the NHBPEP table. Swap in the real percentile
# table if a paediatric unit ever has to report the percentile itself.
_BP_FOR_HEIGHT = {  # field -> (value at 60cm, mmHg gained per cm of height)
    "systolic_bp": ((70, 100), 0.23),
    "diastolic_bp": ((35, 65), 0.185),
}


def _bp_bands_for_height(height_cm):
    """Cuff bands for a child of this height, in cm."""
    # Outside the anchors the fit is extrapolating, so it is held at the ends:
    # a tall teenager is already on the adult numbers the fit converges to.
    over = max(60.0, min(float(height_cm), 168.0)) - 60
    return {
        field: (round(low + rate * over), round(high + rate * over))
        for field, ((low, high), rate) in _BP_FOR_HEIGHT.items()
    }


def triage_bands(age_group, height_cm=None):
    """The bands to judge one patient's vitals by, for their age and size.

    An unknown or adult age group gets the adult bands — a missing date of
    birth must not turn an adult's normal pulse into a flag, and a short adult
    is not a child.
    """
    bands = PAEDIATRIC_TRIAGE_BANDS.get(age_group)
    if bands is None:
        return dict(TRIAGE_BANDS)
    if height_cm:
        bands = {**bands, **_bp_bands_for_height(height_cm)}
    return {**TRIAGE_BANDS, **bands}


class Consultation(PatientLinkedModel, TenantOwnedModel):
    """One clinician-patient encounter: why they came, what was measured, and
    where they went next.

    Deliberately carries no diagnosis and no drug list of its own. The diagnosis
    is a ``CaseReport`` and the drugs are ``Prescription`` rows written against
    that case report — a consultation that duplicated either would give the
    rollups two disagreeing answers for one visit. What lives here is what
    nothing else records: the presenting complaint, the triage vitals, and the
    disposition.

    A consultation is open while the patient is in front of the clinician and
    closed when they leave. A patient has at most one open consultation at a
    time, and a closed one is a signed clinical note that cannot be edited (see
    ``save``) — correcting one means filing a new consultation.
    """

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    class Disposition(models.TextChoices):
        HOME = "home", "Discharged home"
        FOLLOW_UP = "follow_up", "Discharged, follow-up"
        ADMITTED = "admitted", "Admitted"
        REFERRED = "referred", "Referred out"
        DECEASED = "deceased", "Died"

    # How a disposition settles the case report's outcome when the consultation
    # closes. ADMITTED is absent on purpose: an admitted patient's case is still
    # running, so its outcome stays whatever the ward records later.
    OUTCOME_FOR_DISPOSITION = {
        Disposition.HOME: CaseReport.Outcome.RECOVERED,
        Disposition.FOLLOW_UP: CaseReport.Outcome.ONGOING,
        Disposition.REFERRED: CaseReport.Outcome.REFERRED,
        Disposition.DECEASED: CaseReport.Outcome.DECEASED,
    }

    reporter = models.ForeignKey(  # the clinician who saw the patient
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    # The booking this encounter came from. NULL for a walk-in, which is most of
    # an outpatient day — an appointment is never required to be seen.
    appointment = models.ForeignKey(
        "analytics.Appointment", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="consultations",
    )
    # The diagnosis reached. Optional: it is filled during the visit, and a
    # consultation that ended without one is still a consultation.
    case_report = models.ForeignKey(
        "analytics.CaseReport", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="consultations",
    )

    chief_complaint = models.CharField(max_length=255)

    # --- triage vitals. All optional — a consultation is still a consultation
    # when the scale is broken. The validators reject the impossible, not the
    # abnormal; TRIAGE_BANDS is what merely gets flagged.
    temperature_c = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("25")),
                    MaxValueValidator(Decimal("45"))],
    )
    pulse_bpm = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(300)],
    )
    respiratory_rate = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(4), MaxValueValidator(80)],
    )
    systolic_bp = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(50), MaxValueValidator(300)],
    )
    diastolic_bp = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(200)],
    )
    oxygen_saturation = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(50), MaxValueValidator(100)],
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.5")),
                    MaxValueValidator(Decimal("500"))],
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("20")),
                    MaxValueValidator(Decimal("260"))],
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    disposition = models.CharField(
        max_length=20, choices=Disposition.choices, blank=True
    )
    follow_up_on = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    region = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
            models.Index(fields=["tenant", "disposition"]),
            models.Index(fields=["patient", "status"]),
        ]

    def __str__(self):
        return f"Consultation #{self.pk} ({self.status})"

    # --- vitals readouts -------------------------------------------------
    @property
    def bmi(self):
        """Body mass index to one decimal, or None without both measurements."""
        if not (self.weight_kg and self.height_cm):
            return None
        metres = Decimal(self.height_cm) / 100
        return float(round(Decimal(self.weight_kg) / (metres * metres), 1))

    @property
    def blood_pressure(self):
        """Cuff reading as "120/80", or "" when a half of it is missing."""
        if self.systolic_bp and self.diastolic_bp:
            return f"{self.systolic_bp}/{self.diastolic_bp}"
        return ""

    @property
    def abnormal_vitals(self):
        """Names of the recorded vitals outside the triage band for this age.

        Unrecorded vitals are absent, not abnormal — a missing reading and a bad
        one are different problems and only one of them is the patient's.
        """
        out = []
        bands = triage_bands(self.patient_age_group, self.height_cm)
        for field, (low, high) in bands.items():
            value = getattr(self, field)
            if value is None:
                continue
            value = float(value)
            if value < low or value > high:
                out.append(field)
        return out

    # --- lifecycle -------------------------------------------------------
    # The status this row was loaded with, so save() can tell an edit of a
    # closed note from the close that closed it. None on an unsaved row.
    _db_status = None

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        if "status" in field_names:  # not set when the field was deferred
            obj._db_status = values[field_names.index("status")]
        return obj

    def refresh_from_db(self, *args, **kwargs):
        # Field values are copied onto this instance from a freshly loaded one,
        # but _db_status is not a field and would keep the status this row was
        # first loaded with — a note someone else closed meanwhile would still
        # look open, and editable.
        super().refresh_from_db(*args, **kwargs)
        self._db_status = self.status

    def save(self, *args, **kwargs):
        if self._db_status == self.Status.CLOSED:
            raise ValueError(
                "A closed consultation is a signed clinical note and cannot be "
                "edited. File a new consultation instead."
            )
        if self.status == self.Status.OPEN and self.patient_id:
            # One open consultation per patient. Two clinicians writing vitals
            # into two open notes for one person is how half a visit goes
            # missing. Enforced here rather than by a partial unique index,
            # which MySQL has no equivalent for (see CaseReport.source_ref).
            # all_objects, not objects: a patient belongs to one tenant, so
            # this cannot reach across tenants, and the tenant-scoped manager
            # returns nothing at all when no tenant is bound — which would let
            # a shell session or an import quietly open the second note.
            clash = Consultation.all_objects.filter(
                patient_id=self.patient_id, status=self.Status.OPEN
            ).exclude(pk=self.pk)
            if clash.exists():
                raise ValueError(
                    "This patient already has an open consultation. Close that "
                    "one before starting another."
                )
        super().save(*args, **kwargs)
        self._db_status = self.status

    @transaction.atomic
    def close(self, *, disposition, follow_up_on=None, notes=None):
        """End the encounter and settle what the visit decided.

        Marks the booking it came from as attended, and carries the disposition
        through to the case report's outcome so the surveillance rollups agree
        with the note. A death also files a ``VitalEvent``, which is the row the
        mortality ratios are counted from and what closes the patient record.
        """
        if self.status == self.Status.CLOSED:
            raise ValueError("This consultation is already closed.")
        if disposition not in self.Disposition.values:
            raise ValueError(f"Not a disposition: {disposition!r}")
        follow_up = follow_up_on or self.follow_up_on
        if disposition == self.Disposition.FOLLOW_UP and not follow_up:
            raise ValueError("A follow-up disposition needs a follow-up date.")
        self.disposition = disposition
        self.follow_up_on = follow_up
        if notes:
            self.notes = f"{self.notes}\n{notes}".strip()
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save()
        if self.appointment_id:
            appointment = self.appointment
            appointment.status = Appointment.Status.COMPLETED
            appointment.save(update_fields=["status", "updated_at"])
        outcome = self.OUTCOME_FOR_DISPOSITION.get(disposition)
        if outcome and self.case_report_id:
            case = self.case_report
            # Only ever moves a case that is still running: an outcome someone
            # already recorded was entered deliberately and stands.
            if case.outcome == CaseReport.Outcome.ONGOING:
                case.outcome = outcome
                case.save(update_fields=["outcome", "updated_at"])
        if disposition == self.Disposition.DECEASED:
            self._register_death()
        return self

    def _register_death(self):
        """File the death in vital registration, unless it is already there.

        The mortality ratios count ``VitalEvent`` deaths and the patient record
        is closed by one (see ``VitalEvent.save``), so a deceased disposition
        that filed nothing left the patient alive in the registry and the death
        out of the ratios. An unlinked consultation still files the event: it
        carries the age band and region, which is all the rollup counts.

        ``maternal_death`` is left off. Whether a death was related to
        pregnancy is a certification decision, not something a disposition
        knows — whoever certifies it sets the flag on the event.
        """
        # all_objects for the same reason as the open-consultation check: the
        # scoped manager sees nothing without a bound tenant, and a duplicate
        # death is one the mortality ratios would count twice.
        already_filed = self.patient_id and VitalEvent.all_objects.filter(
            patient_id=self.patient_id, event_type=VitalEvent.Kind.DEATH
        ).exists()
        if already_filed:
            return  # someone registered this death already; do not count it twice
        VitalEvent.objects.create(
            tenant=self.tenant,
            patient=self.patient,
            patient_age_group=self.patient_age_group,
            patient_sex=self.patient_sex,
            reporter=self.reporter,
            event_type=VitalEvent.Kind.DEATH,
            cause=self.case_report.disease if self.case_report_id else None,
            infant_death=self.patient_age_group == "0-1",
            region=self.region,
            notes=f"Registered from consultation #{self.pk}.",
        )
