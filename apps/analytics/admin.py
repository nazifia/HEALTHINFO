from django.contrib import admin
from django.contrib.contenttypes.models import ContentType

from apps.governance.models import AuditLog

from .models import (
    AdverseDrugReaction,
    AiInteraction,
    AnalyticsEvent,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    Consultation,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    Prescription,
    StockReport,
    VitalEvent,
)


class AllTenantsAdmin(admin.ModelAdmin):
    """Admin reads across tenants.

    The default manager is tenant-scoped and a session login to /admin binds no
    tenant, so without this every list is empty and no report can be opened to edit.
    """

    def get_queryset(self, request):
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def _audit(self, request, obj, to_status, note=""):
        AuditLog.all_objects.create(
            tenant_id=obj.tenant_id, user=request.user,
            content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk,
            from_status="", to_status=to_status, note=note[:1000],
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._audit(
            request, obj, "admin_edit" if change else "admin_add",
            "Changed: " + ", ".join(form.changed_data) if change else "",
        )

    def delete_model(self, request, obj):
        self._audit(request, obj, "admin_delete")  # before delete: pk is gone after
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self._audit(request, obj, "admin_delete")
        super().delete_queryset(request, queryset)


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(AllTenantsAdmin):
    list_display = ("event_type", "tenant", "user", "query", "object_type", "object_id", "created_at")
    list_filter = ("tenant", "event_type")


@admin.register(AiInteraction)
class AiInteractionAdmin(AllTenantsAdmin):
    list_display = ("question", "tenant", "user", "model_name", "created_at")
    list_filter = ("tenant", "model_name")
    search_fields = ("question", "answer")
    readonly_fields = ("question", "answer", "sources", "model_name", "tenant", "user")


@admin.register(CaseReport)
class CaseReportAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "disease", "severity", "outcome", "created_at")
    list_filter = ("tenant", "severity", "outcome")
    search_fields = ("notes", "patient_age_group")
    raw_id_fields = ("disease", "symptoms", "medications", "reporter")
    # Set once, never cleared (see CaseReport.mark_notified): a notification that
    # went out cannot un-go, so the admin may not edit or blank it.
    readonly_fields = ("notified_at", "notified_by")


@admin.register(AdverseDrugReaction)
class AdverseDrugReactionAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "medication", "reaction", "severity", "outcome", "created_at")
    list_filter = ("tenant", "severity", "outcome")
    search_fields = ("reaction", "notes", "patient_age_group")
    raw_id_fields = ("medication", "reporter")


@admin.register(LabResult)
class LabResultAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "lab_test", "flag", "organism", "antibiotic", "susceptibility", "created_at")
    list_filter = ("tenant", "flag", "susceptibility")
    search_fields = ("organism", "antibiotic", "value", "notes")
    raw_id_fields = ("lab_test", "disease", "reporter")


@admin.register(Immunization)
class ImmunizationAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "vaccine", "dose_number", "patient_age_group", "region", "created_at")
    list_filter = ("tenant", "vaccine")
    search_fields = ("vaccine", "notes")
    raw_id_fields = ("reporter",)


@admin.register(VitalEvent)
class VitalEventAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "event_type", "cause", "maternal_death", "infant_death", "region", "created_at")
    list_filter = ("tenant", "event_type", "maternal_death", "infant_death")
    search_fields = ("notes",)
    raw_id_fields = ("cause", "reporter")


@admin.register(StockReport)
class StockReportAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "medication", "on_hand", "consumed", "shortage", "region", "created_at")
    list_filter = ("tenant", "shortage")
    search_fields = ("notes",)
    raw_id_fields = ("medication", "reporter")


@admin.register(CommunityHealthReport)
class CommunityHealthReportAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "report_type", "danger_signs", "referred", "region", "created_at")
    list_filter = ("tenant", "report_type", "danger_signs", "referred")
    search_fields = ("notes",)
    raw_id_fields = ("reporter",)


@admin.register(FacilityMetric)
class FacilityMetricAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "beds_occupied", "beds_total", "avg_wait_minutes", "staff_on_duty", "patients_treated", "created_at")
    list_filter = ("tenant",)
    raw_id_fields = ("reporter",)


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "diagnosis", "amount", "status", "region", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("notes",)
    raw_id_fields = ("diagnosis", "reporter")


@admin.register(Appointment)
class AppointmentAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "mode", "status", "reason", "region", "created_at")
    list_filter = ("tenant", "mode", "status")
    search_fields = ("reason", "notes")
    raw_id_fields = ("reporter",)


@admin.register(Prescription)
class PrescriptionAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "medication", "dose", "frequency", "duration_days", "status", "dispensed_at", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("dose", "frequency", "notes")
    raw_id_fields = ("medication", "case_report", "reporter")


@admin.register(Consultation)
class ConsultationAdmin(AllTenantsAdmin):
    list_display = ("id", "tenant", "reporter", "patient", "chief_complaint",
                    "status", "disposition", "created_at")
    list_filter = ("tenant", "status", "disposition")
    search_fields = ("chief_complaint", "notes", "patient_age_group")
    raw_id_fields = ("patient", "reporter", "appointment", "case_report")
