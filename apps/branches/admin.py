from django.contrib import admin

from .models import Branch, Shift


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_main", "is_active", "phone")
    list_filter = ("tenant", "is_main", "is_active")
    search_fields = ("name", "address", "phone")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "starts_at", "ends_at", "tenant")
    list_filter = ("tenant", "branch")
    search_fields = ("user__username", "notes")
