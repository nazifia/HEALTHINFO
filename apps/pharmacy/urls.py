"""HMO and claim routes, plus the legacy ``/api/pharmacy/*`` aliases.

Stock and sales now live at ``/api/inventory/*`` and ``/api/pos/*``. The
mobile and web clients were written against ``/api/pharmacy/*``, so the same
viewsets are registered there too: same code, two prefixes, no client to
re-release.

ponytail: aliases, not redirects — a 301 would break the clients' POST bodies.
Drop the alias block once nothing calls the old paths.
"""
from rest_framework.routers import SimpleRouter

from apps.inventory.urls import register as register_inventory
from apps.pos.urls import register as register_pos

from .views import ClaimBatchViewSet, ClaimViewSet, HMOViewSet, HmoEnrollmentViewSet

router = SimpleRouter()
router.register("pharmacy/hmos", HMOViewSet, basename="pharmacy-hmo")
router.register("pharmacy/enrollments", HmoEnrollmentViewSet,
                basename="pharmacy-enrollment")
router.register("pharmacy/claims", ClaimViewSet, basename="pharmacy-claim")
router.register("pharmacy/claim-batches", ClaimBatchViewSet,
                basename="pharmacy-claim-batch")

urlpatterns = (
    router.urls
    + register_inventory("pharmacy", "pharmacy")
    + register_pos("pharmacy", "pharmacy")
)
