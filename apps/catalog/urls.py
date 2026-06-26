from django.urls import path
from rest_framework.routers import SimpleRouter

from .graph import (
    DiseaseGraphView,
    MedicationGraphView,
    ProcedureGraphView,
    SpecialtyGraphView,
)
from .views import (
    ArticleViewSet,
    DifferentialView,
    DiseaseViewSet,
    DrugInteractionViewSet,
    InteractionCheckView,
    LabTestViewSet,
    MedicationViewSet,
    NotifiableReportView,
    ProcedureViewSet,
    SearchView,
    SpecialtyViewSet,
    SymptomViewSet,
)

router = SimpleRouter()
router.register("diseases", DiseaseViewSet, basename="disease")
router.register("medications", MedicationViewSet, basename="medication")
router.register("symptoms", SymptomViewSet, basename="symptom")
router.register("interactions", DrugInteractionViewSet, basename="interaction")
router.register("specialties", SpecialtyViewSet, basename="specialty")
router.register("procedures", ProcedureViewSet, basename="procedure")
router.register("lab-tests", LabTestViewSet, basename="labtest")
router.register("articles", ArticleViewSet, basename="article")

# Custom routes first: "interactions/check/" must beat the router's
# "interactions/<pk>/" detail pattern (its default pk regex would eat "check").
urlpatterns = [
    path("interactions/check/", InteractionCheckView.as_view(), name="interaction-check"),
    path("differential/", DifferentialView.as_view(), name="differential"),
    path("reports/notifiable/", NotifiableReportView.as_view(), name="notifiable-report"),
] + router.urls + [
    path("search/", SearchView.as_view(), name="search"),
    path("graph/diseases/<int:pk>/", DiseaseGraphView.as_view(), name="disease-graph"),
    path(
        "graph/medications/<int:pk>/",
        MedicationGraphView.as_view(),
        name="medication-graph",
    ),
    path(
        "graph/procedures/<int:pk>/",
        ProcedureGraphView.as_view(),
        name="procedure-graph",
    ),
    path(
        "graph/specialties/<int:pk>/",
        SpecialtyGraphView.as_view(),
        name="specialty-graph",
    ),
]
