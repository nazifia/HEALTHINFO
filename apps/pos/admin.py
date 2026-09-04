from django.contrib import admin

from .models import (
    Cashier,
    DispensingLog,
    Expense,
    ExpenseCategory,
    Notification,
    PaymentRequest,
    PaymentRequestItem,
    PurchaseOrder,
    PurchaseOrderLine,
    ReturnRecord,
    Sale,
    SaleItem,
    SalePayment,
    TillSession,
)


@admin.register(Cashier)
class CashierAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "code", "kind", "is_active")
    list_filter = ("tenant", "kind", "is_active")
    search_fields = ("name", "code")
    raw_id_fields = ("user",)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    raw_id_fields = ("item", "batch")
    readonly_fields = ("item", "batch", "quantity", "unit_price", "discount",
                       "cost_price", "return_quantity")


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0
    readonly_fields = ("method", "tendered", "applied", "change", "till_session",
                       "taken_by")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "buyer", "payment_method", "status",
                    "total", "patient_payable", "hmo_payable", "amount_paid",
                    "created_at")
    list_filter = ("tenant", "status", "payment_method", "is_wholesale")
    search_fields = ("reference", "buyer_name")
    raw_id_fields = ("patient", "customer", "branch", "prescription", "rx",
                     "enrollment", "served_by", "cashier")
    inlines = [SaleItemInline, SalePaymentInline]


@admin.register(ReturnRecord)
class ReturnRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "sale", "quantity", "amount", "refund_method",
                    "created_at")
    list_filter = ("tenant", "refund_method")
    raw_id_fields = ("sale", "line", "returned_by")


@admin.register(TillSession)
class TillSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "opened_by", "status", "opening_float",
                    "counted_amount", "closed_at")
    list_filter = ("tenant", "status")
    raw_id_fields = ("opened_by", "branch")


@admin.register(DispensingLog)
class DispensingLogAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "quantity", "amount", "status", "user",
                    "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("name", "brand")
    raw_id_fields = ("sale", "item", "user")
    readonly_fields = ("sale", "item", "user", "name", "brand", "form", "unit",
                       "quantity", "amount", "discount", "tenant")


class PaymentRequestItemInline(admin.TabularInline):
    model = PaymentRequestItem
    extra = 0
    raw_id_fields = ("item",)


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "tenant", "dispenser", "cashier", "status",
                    "total_amount", "created_at")
    list_filter = ("tenant", "status", "store")
    search_fields = ("reference", "buyer_name")
    raw_id_fields = ("dispenser", "cashier", "customer", "patient", "sale")
    inlines = [PaymentRequestItemInline]


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant")
    list_filter = ("tenant",)
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "category", "amount", "payment_source", "date",
                    "created_by")
    list_filter = ("tenant", "payment_source", "category")
    search_fields = ("description",)
    raw_id_fields = ("category", "branch", "till_session", "created_by")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "user", "kind", "priority", "is_read",
                    "created_at")
    list_filter = ("tenant", "kind", "priority", "is_read")
    search_fields = ("title", "message")
    raw_id_fields = ("user", "item")


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
    raw_id_fields = ("supplier", "branch", "ordered_by")
    inlines = [PurchaseOrderLineInline]
