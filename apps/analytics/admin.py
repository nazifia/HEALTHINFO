from django.contrib import admin

from .models import (
    AdverseDrugReaction,
    AiInteraction,
    AnalyticsEvent,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    StockReport,
    VitalEvent,
)


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "tenant", "user", "query", "object_type", "object_id", "created_at")
    list_filter = ("tenant", "event_type")


@admin.register(AiInteraction)
class AiInteractionAdmin(admin.ModelAdmin):
    list_display = ("question", "tenant", "user", "model_name", "feedback", "created_at")
    list_filter = ("tenant", "model_name", "feedback")
    search_fields = ("question", "answer")
    readonly_fields = ("question", "answer", "sources", "model_name", "tenant", "user", "feedback")


@admin.register(CaseReport)
class CaseReportAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "disease", "severity", "outcome", "created_at")
    list_filter = ("tenant", "severity", "outcome")
    search_fields = ("notes", "patient_age_group")
    raw_id_fields = ("disease", "symptoms", "medications", "reporter")


@admin.register(AdverseDrugReaction)
class AdverseDrugReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "medication", "reaction", "severity", "outcome", "created_at")
    list_filter = ("tenant", "severity", "outcome")
    search_fields = ("reaction", "notes", "patient_age_group")
    raw_id_fields = ("medication", "reporter")


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "lab_test", "flag", "organism", "antibiotic", "susceptibility", "created_at")
    list_filter = ("tenant", "flag", "susceptibility")
    search_fields = ("organism", "antibiotic", "value", "notes")
    raw_id_fields = ("lab_test", "disease", "reporter")


@admin.register(Immunization)
class ImmunizationAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "vaccine", "dose_number", "patient_age_group", "region", "created_at")
    list_filter = ("tenant", "vaccine")
    search_fields = ("vaccine", "notes")
    raw_id_fields = ("reporter",)


@admin.register(VitalEvent)
class VitalEventAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "event_type", "cause", "maternal_death", "infant_death", "region", "created_at")
    list_filter = ("tenant", "event_type", "maternal_death", "infant_death")
    search_fields = ("notes",)
    raw_id_fields = ("cause", "reporter")


@admin.register(StockReport)
class StockReportAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "medication", "on_hand", "consumed", "shortage", "region", "created_at")
    list_filter = ("tenant", "shortage")
    search_fields = ("notes",)
    raw_id_fields = ("medication", "reporter")


@admin.register(CommunityHealthReport)
class CommunityHealthReportAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "report_type", "danger_signs", "referred", "region", "created_at")
    list_filter = ("tenant", "report_type", "danger_signs", "referred")
    search_fields = ("notes",)
    raw_id_fields = ("reporter",)


@admin.register(FacilityMetric)
class FacilityMetricAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "beds_occupied", "beds_total", "avg_wait_minutes", "staff_on_duty", "patients_treated", "created_at")
    list_filter = ("tenant",)
    raw_id_fields = ("reporter",)


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "diagnosis", "amount", "status", "region", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("notes",)
    raw_id_fields = ("diagnosis", "reporter")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "reporter", "mode", "status", "reason", "region", "created_at")
    list_filter = ("tenant", "mode", "status")
    search_fields = ("reason", "notes")
    raw_id_fields = ("reporter",)
