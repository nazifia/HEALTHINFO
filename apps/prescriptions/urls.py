from rest_framework.routers import SimpleRouter

from .views import PrescriptionViewSet

router = SimpleRouter()
# Not the bare "prescriptions" prefix: that is the clinical drug order
# (apps.analytics), registered first in the URLconf and matched first. A
# counter script is a different record — a named customer and a list of lines
# to hand over — so it gets its own path instead of a route nothing reaches.
router.register("prescriptions/scripts", PrescriptionViewSet, basename="rx")

urlpatterns = router.urls
