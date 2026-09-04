from django.contrib import admin

from .models import CommissionConfig


@admin.register(CommissionConfig)
class CommissionConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "rate", "fixed_bonus", "is_active")
    list_filter = ("tenant", "is_active")
    raw_id_fields = ("user",)
