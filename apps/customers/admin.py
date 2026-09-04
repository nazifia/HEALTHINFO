from django.contrib import admin

from .models import Customer, WalletTransaction


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "phone", "is_wholesale", "wallet_balance",
                    "outstanding_debt", "is_active")
    list_filter = ("tenant", "is_wholesale", "is_active")
    search_fields = ("name", "phone", "email")
    raw_id_fields = ("patient", "prescriber")
    # Balances are the sum of the wallet ledger; typing over one here would
    # leave the two disagreeing with nothing to say which is right.
    readonly_fields = ("wallet_balance", "outstanding_debt")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "customer", "txn_type", "method", "amount",
                    "created_at")
    list_filter = ("tenant", "txn_type", "method")
    search_fields = ("note",)
    raw_id_fields = ("customer",)
    readonly_fields = ("customer", "txn_type", "method", "amount", "note", "tenant")
