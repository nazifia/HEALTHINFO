from django.contrib import admin

from .models import Jurisdiction, Tenant


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "parent")
    list_filter = ("level",)
    search_fields = ("name",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "name", "slug", "kind", "jurisdiction", "contact", "domain",
        "subscription_plan", "subscription_status", "status",
    )
    list_filter = ("kind", "jurisdiction__level", "subscription_status", "status")
    search_fields = ("name", "slug", "domain", "contact")
    actions = ("approve_subscription", "reject_subscription",
               "mark_hospital", "mark_pharmacy")

    @admin.action(description="Approve selected tenant subscriptions")
    def approve_subscription(self, request, queryset):
        n = queryset.update(subscription_status=Tenant.SubscriptionStatus.APPROVED)
        self.message_user(request, f"{n} subscription(s) approved.")

    @admin.action(description="Reject selected tenant subscriptions")
    def reject_subscription(self, request, queryset):
        n = queryset.update(subscription_status=Tenant.SubscriptionStatus.REJECTED)
        self.message_user(request, f"{n} subscription(s) rejected.")

    @admin.action(description="Mark selected tenants as hospitals")
    def mark_hospital(self, request, queryset):
        n = queryset.update(kind=Tenant.Kind.HOSPITAL)
        self.message_user(request, f"{n} tenant(s) marked as hospitals.")

    @admin.action(description="Mark selected tenants as pharmacies")
    def mark_pharmacy(self, request, queryset):
        n = queryset.update(kind=Tenant.Kind.PHARMACY)
        self.message_user(request, f"{n} tenant(s) marked as pharmacies.")
