from django.core.exceptions import ValidationError
from django.db import models

from apps.tenants.models import SharedCatalogModel


class Status(models.TextChoices):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Symptom(SharedCatalogModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    severity_level = models.PositiveSmallIntegerField(default=1)  # 1=mild .. 5=severe

    class Meta:
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name


class Disease(SharedCatalogModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    icd10_code = models.CharField(max_length=10, blank=True)
    # Notifiable = legally reportable to public-health authorities. Drives the
    # mandatory-report endpoint and raises surveillance priority.
    notifiable = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    causes = models.TextField(blank=True)
    risk_factors = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    treatment = models.TextField(blank=True)
    prevention = models.TextField(blank=True)
    complications = models.TextField(blank=True)
    references = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    # Graph edges. M2M querysets default to the tenant-scoped manager, so the
    # serializer can only ever link nodes from the same tenant.
    symptoms = models.ManyToManyField(Symptom, blank=True, related_name="diseases")
    medications = models.ManyToManyField(
        "Medication", blank=True, related_name="diseases"
    )

    class Meta:
        # Slug unique per tenant, not globally.
        unique_together = ("tenant", "slug")
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name


class Medication(SharedCatalogModel):
    generic_name = models.CharField(max_length=255)
    brand_name = models.CharField(max_length=255, blank=True)
    drug_class = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    indications = models.TextField(blank=True)
    dosage = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    warnings = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    storage_information = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    class Meta:
        indexes = [models.Index(fields=["tenant", "generic_name"])]

    def __str__(self):
        return self.generic_name


class DrugInteraction(SharedCatalogModel):
    class Severity(models.TextChoices):
        MINOR = "minor"
        MODERATE = "moderate"
        MAJOR = "major"

    medication_a = models.ForeignKey(
        Medication, on_delete=models.CASCADE, related_name="interactions_a"
    )
    medication_b = models.ForeignKey(
        Medication, on_delete=models.CASCADE, related_name="interactions_b"
    )
    severity = models.CharField(max_length=20, choices=Severity.choices)
    description = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)

    class Meta:
        unique_together = ("tenant", "medication_a", "medication_b")

    def clean(self):
        if self.medication_a_id == self.medication_b_id:
            raise ValidationError("A drug cannot interact with itself.")
        # Defense in depth: never link meds across tenants.
        if self.medication_a.tenant_id != self.medication_b.tenant_id:
            raise ValidationError("Medications must belong to the same tenant.")

    def save(self, *args, **kwargs):
        # tenant is auto-assigned in TenantOwnedModel.save (runs after this),
        # so skip it here; the DB unique constraint still covers it.
        self.full_clean(exclude=["tenant"])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.medication_a} x {self.medication_b} ({self.severity})"


class Specialty(SharedCatalogModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # No workflow: a reference taxonomy, like Symptom.
    diseases = models.ManyToManyField(Disease, blank=True, related_name="specialties")

    class Meta:
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name


class Procedure(SharedCatalogModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    indications = models.TextField(blank=True)
    preparation = models.TextField(blank=True)
    risks = models.TextField(blank=True)
    recovery = models.TextField(blank=True)
    references = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    diseases = models.ManyToManyField(Disease, blank=True, related_name="procedures")

    class Meta:
        unique_together = ("tenant", "slug")
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name


class LabTest(SharedCatalogModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    purpose = models.TextField(blank=True)
    preparation = models.TextField(blank=True)
    normal_range = models.CharField(max_length=255, blank=True)
    units = models.CharField(max_length=50, blank=True)
    references = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    diseases = models.ManyToManyField(Disease, blank=True, related_name="lab_tests")

    class Meta:
        unique_together = ("tenant", "slug")
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self):
        return self.name


class Article(SharedCatalogModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField()
    summary = models.TextField(blank=True)
    body = models.TextField(blank=True)
    references = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    diseases = models.ManyToManyField(Disease, blank=True, related_name="articles")
    medications = models.ManyToManyField(
        Medication, blank=True, related_name="articles"
    )

    class Meta:
        unique_together = ("tenant", "slug")
        indexes = [models.Index(fields=["tenant", "title"])]

    def __str__(self):
        return self.title
