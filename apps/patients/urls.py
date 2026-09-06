from rest_framework.routers import SimpleRouter

from .portal import PatientPortalViewSet
from .views import PatientViewSet

router = SimpleRouter()
router.register("patients", PatientViewSet, basename="patient")
# The patient's own read-only view of that same record.
router.register("portal", PatientPortalViewSet, basename="portal")

urlpatterns = router.urls
