from rest_framework.routers import SimpleRouter

from .views import TenantViewSet

router = SimpleRouter()
router.register("tenants", TenantViewSet, basename="tenant")

urlpatterns = router.urls
