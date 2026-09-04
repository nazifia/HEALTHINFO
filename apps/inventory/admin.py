from django.contrib import admin

from .models import (
    StockBatch,
    StockCheck,
    StockCheckItem,
    StockItem,
    StockMovement,
    Supplier,
    TransferRequest,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "contact_person", "phone", "email",
                    "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "contact_person", "phone", "email")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "sku", "form", "store", "unit_price",
                    "reorder_level", "quantity_on_hand", "is_active")
    list_filter = ("tenant", "form", "store", "is_active", "prescription_only")
    search_fields = ("name", "brand", "sku", "barcode")
    raw_id_fields = ("medication", "branch")


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ("batch_number", "tenant", "item", "quantity", "expiry_date",
                    "supplier", "cost_price")
    list_filter = ("tenant", "expiry_date")
    search_fields = ("batch_number", "supplier__name")
    raw_id_fields = ("item", "supplier")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "item", "batch", "kind", "quantity", "user",
                    "created_at")
    list_filter = ("tenant", "kind")
    search_fields = ("reason",)
    raw_id_fields = ("item", "batch", "sale", "user")
    # The ledger is the audit trail — the admin reads it, it does not edit it.
    readonly_fields = ("item", "batch", "kind", "quantity", "sale", "user", "reason",
                       "tenant")


class StockCheckItemInline(admin.TabularInline):
    model = StockCheckItem
    extra = 0
    raw_id_fields = ("item",)
    readonly_fields = ("expected_quantity",)


@admin.register(StockCheck)
class StockCheckAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "store", "status", "created_by", "approved_by",
                    "created_at")
    list_filter = ("tenant", "status", "store")
    raw_id_fields = ("branch", "created_by", "approved_by")
    inlines = [StockCheckItemInline]


@admin.register(TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "from_item", "to_item", "requested_quantity",
                    "approved_quantity", "status", "created_at")
    list_filter = ("tenant", "status")
    raw_id_fields = ("from_item", "to_item", "requested_by", "approved_by")
