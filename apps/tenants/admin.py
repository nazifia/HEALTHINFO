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
        "name", "slug", "jurisdiction", "contact", "domain",
        "subscription_plan", "subscription_status", "status",
    )
    list_filter = ("jurisdiction__level", "subscription_status", "status")
    search_fields = ("name", "slug", "domain", "contact")
    actions = ("approve_subscription", "reject_subscription")

    @admin.action(description="Approve selected tenant subscriptions")
    def approve_subscription(self, request, queryset):
        n = queryset.update(subscription_status=Tenant.SubscriptionStatus.APPROVED)
        self.message_user(request, f"{n} subscription(s) approved.")

    @admin.action(description="Reject selected tenant subscriptions")
    def reject_subscription(self, request, queryset):
        n = queryset.update(subscription_status=Tenant.SubscriptionStatus.REJECTED)
        self.message_user(request, f"{n} subscription(s) rejected.")
