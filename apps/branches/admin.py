from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_main", "is_active", "phone")
    list_filter = ("tenant", "is_main", "is_active")
    search_fields = ("name", "address", "phone")
