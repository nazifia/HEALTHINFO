from django.contrib import admin

from .models import (
    HMO,
    Claim,
    HmoEnrollment,
    HmoItemRule,
    PreAuthorization,
    PreAuthorizationItem,
)


class HmoItemRuleInline(admin.TabularInline):
    """Per-drug cover, edited where the scheme itself is."""

    model = HmoItemRule
    extra = 0
    raw_id_fields = ("item",)


@admin.register(HMO)
class HMOAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "code", "coverage_percent",
                    "preauth_threshold", "auto_submit_claims", "is_active")
    list_filter = ("tenant", "auto_submit_claims", "is_active")
    search_fields = ("name", "code")
    inlines = [HmoItemRuleInline]


@admin.register(HmoEnrollment)
class HmoEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("member_number", "tenant", "patient", "hmo", "plan",
                    "coverage_percent", "annual_limit", "is_active")
    list_filter = ("tenant", "hmo", "is_active")
    search_fields = ("member_number", "plan")
    raw_id_fields = ("patient", "hmo")


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "sale", "status", "amount",
                    "amount_approved", "amount_paid", "submitted_at")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "sale__reference")
    raw_id_fields = ("sale", "hmo", "enrollment")


@admin.register(HmoItemRule)
class HmoItemRuleAdmin(admin.ModelAdmin):
    list_display = ("hmo", "tenant", "item", "coverage_percent", "tariff", "note")
    list_filter = ("tenant", "hmo")
    search_fields = ("item__name", "note")
    raw_id_fields = ("hmo", "item")


class PreAuthorizationItemInline(admin.TabularInline):
    """The ordered medications, decided where the request is."""

    model = PreAuthorizationItem
    extra = 0
    raw_id_fields = ("item",)


@admin.register(PreAuthorization)
class PreAuthorizationAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "enrollment", "status",
                    "amount", "amount_approved", "code", "expires_on")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "code", "notes")
    raw_id_fields = ("hmo", "enrollment")
    inlines = [PreAuthorizationItemInline]
