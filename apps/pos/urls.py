"""Point-of-sale routes.

Registered twice by ``config.urls``: once under ``pos/`` (PharmApp's layout)
and once under ``pharmacy/`` (what the mobile and web clients already call).
"""
from rest_framework.routers import SimpleRouter

from .views import (
    CashierViewSet,
    DispensingLogViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    NotificationViewSet,
    PaymentRequestViewSet,
    PurchaseOrderViewSet,
    ReturnRecordViewSet,
    SaleViewSet,
    TillSessionViewSet,
)


def register(prefix, name):
    router = SimpleRouter()
    router.register(f"{prefix}/sales", SaleViewSet, basename=f"{name}-sale")
    router.register(f"{prefix}/returns", ReturnRecordViewSet,
                    basename=f"{name}-return")
    router.register(f"{prefix}/cashiers", CashierViewSet, basename=f"{name}-cashier")
    router.register(f"{prefix}/till-sessions", TillSessionViewSet,
                    basename=f"{name}-till-session")
    router.register(f"{prefix}/dispensing-log", DispensingLogViewSet,
                    basename=f"{name}-dispensing-log")
    router.register(f"{prefix}/payment-requests", PaymentRequestViewSet,
                    basename=f"{name}-payment-request")
    router.register(f"{prefix}/expense-categories", ExpenseCategoryViewSet,
                    basename=f"{name}-expense-category")
    router.register(f"{prefix}/expenses", ExpenseViewSet, basename=f"{name}-expense")
    router.register(f"{prefix}/notifications", NotificationViewSet,
                    basename=f"{name}-notification")
    router.register(f"{prefix}/purchase-orders", PurchaseOrderViewSet,
                    basename=f"{name}-purchase-order")
    return router.urls


urlpatterns = register("pos", "pos")
