from rest_framework.routers import SimpleRouter

from .views import (
    ClaimBatchViewSet,
    ClaimViewSet,
    HMOViewSet,
    HmoEnrollmentViewSet,
    PurchaseOrderViewSet,
    SaleViewSet,
    StockBatchViewSet,
    StockItemViewSet,
    StockMovementViewSet,
    SupplierViewSet,
    TillSessionViewSet,
)

router = SimpleRouter()
router.register("pharmacy/items", StockItemViewSet, basename="pharmacy-item")
router.register("pharmacy/batches", StockBatchViewSet, basename="pharmacy-batch")
router.register("pharmacy/movements", StockMovementViewSet,
                basename="pharmacy-movement")
router.register("pharmacy/suppliers", SupplierViewSet, basename="pharmacy-supplier")
router.register("pharmacy/purchase-orders", PurchaseOrderViewSet,
                basename="pharmacy-purchase-order")
router.register("pharmacy/hmos", HMOViewSet, basename="pharmacy-hmo")
router.register("pharmacy/enrollments", HmoEnrollmentViewSet,
                basename="pharmacy-enrollment")
router.register("pharmacy/sales", SaleViewSet, basename="pharmacy-sale")
router.register("pharmacy/till-sessions", TillSessionViewSet,
                basename="pharmacy-till-session")
router.register("pharmacy/claims", ClaimViewSet, basename="pharmacy-claim")
router.register("pharmacy/claim-batches", ClaimBatchViewSet,
                basename="pharmacy-claim-batch")

urlpatterns = router.urls
