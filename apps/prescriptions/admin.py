from django.contrib import admin

from .models import (
    ConsultationPayout,
    Hospital,
    Prescriber,
    PrescriberCommission,
    Prescription,
    PrescriptionItem,
)


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "city", "phone")
    list_filter = ("tenant",)
    search_fields = ("name", "city")


@admin.register(Prescriber)
class PrescriberAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "license_number", "hospital",
                    "commission_rate", "is_verified", "is_active")
    list_filter = ("tenant", "is_verified", "is_active")
    search_fields = ("name", "license_number", "specialty")
    raw_id_fields = ("hospital",)


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0
    raw_id_fields = ("item", "dispensed_by")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "customer_name", "prescriber", "status",
                    "consultation_fee", "created_at")
    list_filter = ("tenant", "status", "source")
    search_fields = ("customer_name", "customer_phone", "doctor_name")
    raw_id_fields = ("branch", "customer", "patient", "prescriber", "created_by")
    inlines = [PrescriptionItemInline]


@admin.register(PrescriberCommission)
class PrescriberCommissionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "prescriber", "prescription",
                    "commission_amount", "status", "paid_at")
    list_filter = ("tenant", "status")
    raw_id_fields = ("prescriber", "prescription", "sale")


@admin.register(ConsultationPayout)
class ConsultationPayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "prescriber", "prescription",
                    "consultation_fee", "status", "paid_at")
    list_filter = ("tenant", "status")
    raw_id_fields = ("prescriber", "prescription")
