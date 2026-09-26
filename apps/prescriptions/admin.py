from django.contrib import admin

from .models import Prescription, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0
    raw_id_fields = ("item", "dispensed_by")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "customer_name", "doctor_name", "status",
                    "created_at")
    list_filter = ("tenant", "status", "source")
    search_fields = ("customer_name", "customer_phone", "doctor_name")
    raw_id_fields = ("branch", "customer", "patient", "created_by")
    inlines = [PrescriptionItemInline]
