from django.contrib import admin

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


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "icd10_code", "status")
    list_filter = ("tenant", "status")
    search_fields = ("name", "icd10_code")


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ("generic_name", "brand_name", "tenant", "status")
    list_filter = ("tenant", "status")
    search_fields = ("generic_name", "brand_name")


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "severity_level")
    list_filter = ("tenant",)
    search_fields = ("name",)


@admin.register(DrugInteraction)
class DrugInteractionAdmin(admin.ModelAdmin):
    list_display = ("medication_a", "medication_b", "tenant", "severity")
    list_filter = ("tenant", "severity")


@admin.register(Specialty)
class SpecialtyAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant")
    list_filter = ("tenant",)
    search_fields = ("name",)


@admin.register(Procedure)
class ProcedureAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "status")
    list_filter = ("tenant", "status")
    search_fields = ("name",)


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "status")
    list_filter = ("tenant", "status")
    search_fields = ("name",)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "status")
    list_filter = ("tenant", "status")
    search_fields = ("title",)
