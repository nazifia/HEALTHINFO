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
        "subscription_plan", "status",
    )
    list_filter = ("jurisdiction__level", "status")
    search_fields = ("name", "slug", "domain", "contact")
