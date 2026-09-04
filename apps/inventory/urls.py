"""Inventory routes.

Registered twice by ``config.urls``: once under ``inventory/`` (PharmApp's
layout) and once under ``pharmacy/`` (what the mobile and web clients already
call). ``register`` builds a fresh router each time so the two prefixes cannot
share basenames and collide in the URL names.
"""
from rest_framework.routers import SimpleRouter

from .views import (
    StockBatchViewSet,
    StockCheckViewSet,
    StockItemViewSet,
    StockMovementViewSet,
    SupplierViewSet,
    TransferRequestViewSet,
)


def register(prefix, name):
    router = SimpleRouter()
    router.register(f"{prefix}/items", StockItemViewSet, basename=f"{name}-item")
    router.register(f"{prefix}/batches", StockBatchViewSet, basename=f"{name}-batch")
    router.register(f"{prefix}/movements", StockMovementViewSet,
                    basename=f"{name}-movement")
    router.register(f"{prefix}/suppliers", SupplierViewSet,
                    basename=f"{name}-supplier")
    router.register(f"{prefix}/stock-checks", StockCheckViewSet,
                    basename=f"{name}-stock-check")
    router.register(f"{prefix}/transfers", TransferRequestViewSet,
                    basename=f"{name}-transfer")
    return router.urls


urlpatterns = register("inventory", "inventory")
