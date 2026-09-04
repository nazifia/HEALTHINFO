from rest_framework.routers import SimpleRouter

from .views import (
    ConsultationPayoutViewSet,
    HospitalViewSet,
    PrescriberCommissionViewSet,
    PrescriberViewSet,
    PrescriptionViewSet,
)

router = SimpleRouter()
router.register("prescriptions/hospitals", HospitalViewSet, basename="rx-hospital")
router.register("prescriptions/prescribers", PrescriberViewSet,
                basename="rx-prescriber")
router.register("prescriptions/commissions", PrescriberCommissionViewSet,
                basename="rx-commission")
router.register("prescriptions/consultation-payouts", ConsultationPayoutViewSet,
                basename="rx-consultation-payout")
# Last: the bare prefix would otherwise swallow the nested ones above.
router.register("prescriptions", PrescriptionViewSet, basename="rx")

urlpatterns = router.urls
