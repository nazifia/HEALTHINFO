from django.contrib import admin

from .models import AuditLog, RuntimeConfig


@admin.register(RuntimeConfig)
class RuntimeConfigAdmin(admin.ModelAdmin):
    list_display = ("mode", "updated_at")

    def has_add_permission(self, request):
        # Singleton: only one row, seeded by migration.
        return not RuntimeConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "from_status", "to_status", "user", "created_at")
    list_filter = ("to_status", "content_type")
    readonly_fields = [f.name for f in AuditLog._meta.fields]  # append-only

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
