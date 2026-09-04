from django.db import models
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
