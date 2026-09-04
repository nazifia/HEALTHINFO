from rest_framework.routers import SimpleRouter

from .views import CustomerViewSet, WalletTransactionViewSet

router = SimpleRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("wallet-transactions", WalletTransactionViewSet,
                basename="wallet-transaction")

urlpatterns = router.urls
