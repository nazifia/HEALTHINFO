from django.contrib import admin

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    PurchaseOrder,
    PurchaseOrderLine,
    Sale,
    SaleItem,
    StockBatch,
    StockItem,
    StockMovement,
    Supplier,
)


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "sku", "form", "unit_price", "reorder_level",
                    "quantity_on_hand", "is_active")
    list_filter = ("tenant", "form", "is_active", "prescription_only")
    search_fields = ("name", "sku")
    raw_id_fields = ("medication",)


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ("batch_number", "tenant", "item", "quantity", "expiry_date",
                    "supplier", "cost_price")
    list_filter = ("tenant", "expiry_date")
    search_fields = ("batch_number", "supplier")
    raw_id_fields = ("item",)


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


@admin.register(HMO)
class HMOAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "code", "coverage_percent", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "code")


@admin.register(HmoEnrollment)
class HmoEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("member_number", "tenant", "patient", "hmo", "plan",
                    "coverage_percent", "is_active")
    list_filter = ("tenant", "hmo", "is_active")
    search_fields = ("member_number", "plan")
    raw_id_fields = ("patient", "hmo")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    raw_id_fields = ("item", "batch")
    readonly_fields = ("item", "batch", "quantity", "unit_price", "discount",
                       "cost_price")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "patient", "payment_method", "status",
                    "total", "patient_payable", "hmo_payable", "amount_paid",
                    "created_at")
    list_filter = ("tenant", "status", "payment_method")
    search_fields = ("reference",)
    raw_id_fields = ("patient", "prescription", "enrollment", "served_by")
    inlines = [SaleItemInline]


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "sale", "status", "amount",
                    "amount_approved", "amount_paid", "submitted_at")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "sale__reference")
    raw_id_fields = ("sale", "hmo", "enrollment")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "contact_person", "phone", "email",
                    "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "contact_person", "phone", "email")


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    raw_id_fields = ("item",)
    readonly_fields = ("quantity_received",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "supplier", "status", "expected_date",
                    "total_cost", "created_at")
    list_filter = ("tenant", "status", "supplier")
    search_fields = ("reference", "notes")
    raw_id_fields = ("supplier", "ordered_by")
    inlines = [PurchaseOrderLineInline]


@admin.register(ClaimBatch)
class ClaimBatchAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "hmo", "status", "period_start",
                    "period_end", "submitted_at")
    list_filter = ("tenant", "status", "hmo")
    search_fields = ("reference", "notes")
    raw_id_fields = ("hmo",)
