from django.contrib import admin

from .models import Patient, PatientAccessLog


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("hospital_number", "full_name", "sex", "date_of_birth",
                    "status", "tenant", "created_at")
    list_filter = ("tenant", "sex", "status", "blood_group", "genotype")
    search_fields = ("hospital_number", "first_name", "last_name", "phone",
                     "nhis_number")
    raw_id_fields = ("chronic_conditions", "registered_by")


@admin.register(PatientAccessLog)
class PatientAccessLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "patient", "query",
                    "result_count", "tenant")
    list_filter = ("tenant", "action")
    search_fields = ("query",)
    raw_id_fields = ("user", "patient")
    # Append-only: the log is evidence, so the admin can read it but not edit it.
    readonly_fields = [f.name for f in PatientAccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
