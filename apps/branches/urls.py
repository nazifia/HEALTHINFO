from rest_framework.routers import SimpleRouter

from .views import BranchViewSet, ShiftViewSet

router = SimpleRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("shifts", ShiftViewSet, basename="shift")

urlpatterns = router.urls
