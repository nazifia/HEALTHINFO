from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    AdrStatsView,
    AdverseDrugReactionViewSet,
    AiFeedbackView,
    AiQualityView,
    AppointmentStatsView,
    AppointmentViewSet,
    BenchmarkView,
    CaseReportExportView,
    CaseReportViewSet,
    ChwStatsView,
    CommunityHealthReportViewSet,
    FacilityMetricViewSet,
    FacilityStatsView,
    FunnelView,
    IdsrReportView,
    ImmunizationStatsView,
    ImmunizationViewSet,
    InsuranceClaimViewSet,
    InsuranceStatsView,
    LabResultViewSet,
    LabStatsView,
    PlatformAdrStatsView,
    PlatformAppointmentStatsView,
    PlatformChwStatsView,
    PlatformFacilityStatsView,
    PlatformIdsrReportView,
    PlatformImmunizationStatsView,
    PlatformInsuranceStatsView,
    PlatformLabStatsView,
    PlatformCaseReportStatsView,
    PlatformDashboardView,
    PlatformReportSourcesView,
    PlatformSpikesView,
    PlatformStockStatsView,
    PlatformVitalStatsView,
    ReportSourcesView,
    RetentionView,
    StockReportViewSet,
    StockStatsView,
    TenantCaseReportStatsView,
    TenantDashboardView,
    TenantSpikesView,
    VitalEventViewSet,
    VitalStatsView,
)

router = SimpleRouter()
router.register("case-reports", CaseReportViewSet, basename="case-report")
router.register("adverse-reactions", AdverseDrugReactionViewSet, basename="adr")
router.register("lab-results", LabResultViewSet, basename="lab-result")
router.register("immunizations", ImmunizationViewSet, basename="immunization")
router.register("vital-events", VitalEventViewSet, basename="vital-event")
router.register("stock-reports", StockReportViewSet, basename="stock-report")
router.register("chw-reports", CommunityHealthReportViewSet, basename="chw-report")
router.register("facility-metrics", FacilityMetricViewSet, basename="facility-metric")
router.register("insurance-claims", InsuranceClaimViewSet, basename="insurance-claim")
router.register("appointments", AppointmentViewSet, basename="appointment")

urlpatterns = router.urls + [
    path("analytics/tenant/", TenantDashboardView.as_view(), name="tenant-dashboard"),
    path("analytics/platform/", PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("analytics/funnel/", FunnelView.as_view(), name="funnel"),
    path("analytics/ai-quality/", AiQualityView.as_view(), name="ai-quality"),
    path("analytics/retention/", RetentionView.as_view(), name="retention"),
    path("analytics/benchmark/", BenchmarkView.as_view(), name="benchmark"),
    path("analytics/surveillance/", TenantSpikesView.as_view(), name="tenant-spikes"),
    path(
        "analytics/platform/surveillance/",
        PlatformSpikesView.as_view(),
        name="platform-spikes",
    ),
    path("analytics/ai/<int:pk>/feedback/", AiFeedbackView.as_view(), name="ai-feedback"),
    path("analytics/cases/", TenantCaseReportStatsView.as_view(), name="tenant-case-stats"),
    path("analytics/cases/export/", CaseReportExportView.as_view(), name="case-export"),
    path(
        "analytics/platform/cases/",
        PlatformCaseReportStatsView.as_view(),
        name="platform-case-stats",
    ),
    path("analytics/sources/", ReportSourcesView.as_view(), name="report-sources"),
    path(
        "analytics/platform/sources/",
        PlatformReportSourcesView.as_view(),
        name="platform-report-sources",
    ),
    path("analytics/idsr/", IdsrReportView.as_view(), name="idsr-report"),
    path(
        "analytics/platform/idsr/",
        PlatformIdsrReportView.as_view(),
        name="platform-idsr-report",
    ),
    path("analytics/adr/", AdrStatsView.as_view(), name="adr-stats"),
    path(
        "analytics/platform/adr/",
        PlatformAdrStatsView.as_view(),
        name="platform-adr-stats",
    ),
    path("analytics/labs/", LabStatsView.as_view(), name="lab-stats"),
    path(
        "analytics/platform/labs/",
        PlatformLabStatsView.as_view(),
        name="platform-lab-stats",
    ),
    path("analytics/immunizations/", ImmunizationStatsView.as_view(), name="immunization-stats"),
    path(
        "analytics/platform/immunizations/",
        PlatformImmunizationStatsView.as_view(),
        name="platform-immunization-stats",
    ),
    path("analytics/vitals/", VitalStatsView.as_view(), name="vital-stats"),
    path(
        "analytics/platform/vitals/",
        PlatformVitalStatsView.as_view(),
        name="platform-vital-stats",
    ),
    path("analytics/stock/", StockStatsView.as_view(), name="stock-stats"),
    path(
        "analytics/platform/stock/",
        PlatformStockStatsView.as_view(),
        name="platform-stock-stats",
    ),
    path("analytics/chw/", ChwStatsView.as_view(), name="chw-stats"),
    path(
        "analytics/platform/chw/",
        PlatformChwStatsView.as_view(),
        name="platform-chw-stats",
    ),
    path("analytics/facility/", FacilityStatsView.as_view(), name="facility-stats"),
    path(
        "analytics/platform/facility/",
        PlatformFacilityStatsView.as_view(),
        name="platform-facility-stats",
    ),
    path("analytics/insurance/", InsuranceStatsView.as_view(), name="insurance-stats"),
    path(
        "analytics/platform/insurance/",
        PlatformInsuranceStatsView.as_view(),
        name="platform-insurance-stats",
    ),
    path("analytics/appointments/", AppointmentStatsView.as_view(), name="appointment-stats"),
    path(
        "analytics/platform/appointments/",
        PlatformAppointmentStatsView.as_view(),
        name="platform-appointment-stats",
    ),
]
