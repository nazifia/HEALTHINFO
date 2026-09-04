from django.contrib import admin

from .models import HMO, Claim, ClaimBatch, HmoEnrollment


@admin.register(HMO)
class HMOAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "code", "coverage_percent",
                    "auto_submit_claims", "is_active")
    list_filter = ("tenant", "auto_submit_claims", "is_active")
    search_fields = ("name", "code")


@admin.register(HmoEnrollment)
class HmoEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("member_number", "tenant", "patient", "hmo", "plan",
                    "coverage_percent", "is_active")
    list_filter = ("tenant", "hmo", "is_active")
    search_fields = ("member_number", "plan")
    raw_id_fields = ("patient", "hmo")


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "sale", "status", "amount",
                    "amount_approved", "amount_paid", "submitted_at")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "sale__reference")
    raw_id_fields = ("sale", "hmo", "enrollment", "batch")


@admin.register(ClaimBatch)
class ClaimBatchAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "status", "period_start",
                    "period_end", "submitted_at")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "notes")
    raw_id_fields = ("hmo",)
