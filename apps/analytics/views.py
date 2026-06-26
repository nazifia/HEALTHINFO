from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from config.responses import success

from apps.accounts.permissions import (
    IsSuperAdmin,
    IsTenantMember,
    ReadOnlyOrReportRole,
)

from .export import case_reports_csv, csv_response
from .idsr import SUMMARY_COLUMNS, platform_idsr_report, tenant_idsr_report
from .models import (
    AdverseDrugReaction,
    AiInteraction,
    Appointment,
    CaseReport,
    CommunityHealthReport,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    StockReport,
    VitalEvent,
)
from .serializers import (
    AdverseDrugReactionSerializer,
    AppointmentSerializer,
    CaseReportSerializer,
    CommunityHealthReportSerializer,
    FacilityMetricSerializer,
    ImmunizationSerializer,
    InsuranceClaimSerializer,
    LabResultSerializer,
    StockReportSerializer,
    VitalEventSerializer,
)
from .stats import (
    adr_stats,
    ai_quality_stats,
    appointment_stats,
    benchmark_stats,
    case_report_stats,
    chw_stats,
    facility_stats,
    funnel_stats,
    immunization_stats,
    insurance_stats,
    lab_stats,
    platform_case_report_stats,
    platform_stats,
    report_sources,
    retention_stats,
    stock_stats,
    tenant_stats,
    vital_stats,
)
from .surveillance import platform_spikes, tenant_spikes


def _range(request):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD into date objects (None if absent)."""
    return (
        parse_date(request.query_params.get("from", "") or ""),
        parse_date(request.query_params.get("to", "") or ""),
    )


class TenantDashboardView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(tenant_stats(*_range(request)))


class PlatformDashboardView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(platform_stats(*_range(request)))


class FunnelView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(funnel_stats(*_range(request)))


class AiQualityView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(ai_quality_stats(*_range(request)))


class RetentionView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(retention_stats())


class BenchmarkView(APIView):
    """Your case load vs the anonymized platform median."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(benchmark_stats())


class TenantSpikesView(APIView):
    """Outbreak alerts for the current tenant."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response({"alerts": tenant_spikes()})


class PlatformSpikesView(APIView):
    """Cross-tenant outbreak alerts (super-admin)."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response({"alerts": platform_spikes()})


class AiFeedbackView(APIView):
    """Thumbs up/down on a RAG answer. Tenant-scoped manager means a member can
    only rate interactions belonging to their own tenant."""

    permission_classes = [IsTenantMember]

    def post(self, request, pk):
        vote = request.data.get("vote")
        if vote not in (AiInteraction.UP, AiInteraction.DOWN):
            raise ValidationError("vote must be 'up' or 'down'")
        updated = AiInteraction.objects.filter(pk=pk).update(feedback=vote)
        if not updated:
            raise NotFound("Interaction not found")
        return success("Thanks for the feedback.", {"vote": vote})


class CaseReportViewSet(viewsets.ModelViewSet):
    """Staff file/list case reports for their own tenant.

    Manager is tenant-scoped, so a member never sees another tenant's reports.
    reporter is stamped server-side from the authenticated user.
    """

    serializer_class = CaseReportSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrReportRole]
    filterset_fields = ("severity", "outcome", "disease", "patient_age_group", "region")
    ordering_fields = ("created_at", "severity")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        return CaseReport.objects.all()

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class AdverseDrugReactionViewSet(viewsets.ModelViewSet):
    """Staff file/list adverse drug reactions (pharmacovigilance), tenant-scoped."""

    serializer_class = AdverseDrugReactionSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrReportRole]
    filterset_fields = ("severity", "outcome", "medication", "region")
    ordering_fields = ("created_at", "severity")

    def get_queryset(self):
        return AdverseDrugReaction.objects.all()

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class _ReportViewSet(viewsets.ModelViewSet):
    """Shared base for staff-filed, tenant-scoped reports.

    Each subclass sets ``model`` + ``serializer_class``; the manager is
    tenant-scoped so a member never sees another tenant's rows, and ``reporter``
    is stamped server-side. Same contract as CaseReportViewSet, factored out so
    the public-health report types don't each repeat it.
    """

    model = None
    permission_classes = [IsTenantMember, ReadOnlyOrReportRole]
    ordering_fields = ("created_at",)

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        return self.model.objects.all()

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class LabResultViewSet(_ReportViewSet):
    """Staff file/list laboratory results (incl. AMR isolates), tenant-scoped."""

    model = LabResult
    serializer_class = LabResultSerializer
    filterset_fields = ("flag", "lab_test", "disease", "organism", "region")


class ImmunizationViewSet(_ReportViewSet):
    """Staff file/list vaccine doses — the immunization registry, tenant-scoped."""

    model = Immunization
    serializer_class = ImmunizationSerializer
    filterset_fields = ("vaccine", "dose_number", "patient_age_group", "region")


class VitalEventViewSet(_ReportViewSet):
    """Staff file/list births & deaths — vital registration, tenant-scoped."""

    model = VitalEvent
    serializer_class = VitalEventSerializer
    filterset_fields = ("event_type", "maternal_death", "infant_death", "region")


class StockReportViewSet(_ReportViewSet):
    """Staff file/list pharmacy stock & usage snapshots, tenant-scoped."""

    model = StockReport
    serializer_class = StockReportSerializer
    filterset_fields = ("medication", "shortage", "region")


class CommunityHealthReportViewSet(_ReportViewSet):
    """CHW field reports (pregnancy, newborn, malnutrition, home deaths)."""

    model = CommunityHealthReport
    serializer_class = CommunityHealthReportSerializer
    filterset_fields = ("report_type", "danger_signs", "referred", "region")


class FacilityMetricViewSet(_ReportViewSet):
    """Daily facility KPI snapshots (beds, waiting time, staffing, throughput)."""

    model = FacilityMetric
    serializer_class = FacilityMetricSerializer
    filterset_fields = ("region",)


class InsuranceClaimViewSet(_ReportViewSet):
    """Health-insurance claims, tenant-scoped."""

    model = InsuranceClaim
    serializer_class = InsuranceClaimSerializer
    filterset_fields = ("status", "diagnosis", "region")


class AppointmentViewSet(_ReportViewSet):
    """Appointments / telemedicine encounters, tenant-scoped."""

    model = Appointment
    serializer_class = AppointmentSerializer
    filterset_fields = ("mode", "status", "region")


class _StatsView(APIView):
    """GET a stats rollup. Tenant-scoped by default; the platform subclass flips
    ``platform=True`` and gates on super-admin."""

    permission_classes = [IsTenantMember]
    stats_fn = None
    platform = False

    def get(self, request):
        return Response(self.stats_fn(*_range(request), platform=self.platform))


class LabStatsView(_StatsView):
    stats_fn = staticmethod(lab_stats)


class PlatformLabStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(lab_stats)


class ImmunizationStatsView(_StatsView):
    stats_fn = staticmethod(immunization_stats)


class PlatformImmunizationStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(immunization_stats)


class VitalStatsView(_StatsView):
    stats_fn = staticmethod(vital_stats)


class PlatformVitalStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(vital_stats)


class StockStatsView(_StatsView):
    stats_fn = staticmethod(stock_stats)


class PlatformStockStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(stock_stats)


class ChwStatsView(_StatsView):
    stats_fn = staticmethod(chw_stats)


class PlatformChwStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(chw_stats)


class FacilityStatsView(_StatsView):
    stats_fn = staticmethod(facility_stats)


class PlatformFacilityStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(facility_stats)


class InsuranceStatsView(_StatsView):
    stats_fn = staticmethod(insurance_stats)


class PlatformInsuranceStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(insurance_stats)


class AppointmentStatsView(_StatsView):
    stats_fn = staticmethod(appointment_stats)


class PlatformAppointmentStatsView(_StatsView):
    permission_classes = [IsSuperAdmin]
    platform = True
    stats_fn = staticmethod(appointment_stats)


class TenantCaseReportStatsView(APIView):
    """Current tenant's case rollup."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(case_report_stats(*_range(request)))


class PlatformCaseReportStatsView(APIView):
    """Central collation of all tenants' case reports for analysis (super-admin)."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(platform_case_report_stats(*_range(request)))


class AdrStatsView(APIView):
    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(adr_stats(*_range(request)))


class PlatformAdrStatsView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(adr_stats(*_range(request), platform=True))


class ReportSourcesView(APIView):
    """Current tenant's report sources — who filed reports and from where."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        return Response(report_sources(*_range(request)))


class PlatformReportSourcesView(APIView):
    """Cross-tenant report sources (super-admin) — origins of all reports."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        return Response(report_sources(*_range(request), platform=True))


def _weeks(request):
    """?weeks=N as a positive int, default 8. Bad input → 400, not 500."""
    raw = request.query_params.get("weeks")
    if raw is None:
        return 8
    try:
        n = int(raw)
    except ValueError:
        raise ValidationError("weeks must be an integer")
    if n < 1:
        raise ValidationError("weeks must be >= 1")
    return n


def _idsr_response(report, request):
    """Render an IDSR report dict as JSON, or its weekly summary as CSV when
    ?format=csv. CSV carries the line-list rows; tier rollups are JSON-only."""
    if request.query_params.get("format") == "csv":
        rows = (
            [r[c] for c in SUMMARY_COLUMNS] for r in report["summary"]
        )
        return csv_response("idsr_weekly_summary.csv", SUMMARY_COLUMNS, rows)
    return Response(report)


class IdsrReportView(APIView):
    """This facility's (tenant's) IDSR weekly epidemiological summary.

    ?weeks=N windows the trailing period (default 8). ?format=csv downloads the
    line-list public-health authorities expect.
    """

    permission_classes = [IsTenantMember]

    def get(self, request):
        weeks = _weeks(request)
        return _idsr_response(tenant_idsr_report(weeks), request)


class PlatformIdsrReportView(APIView):
    """Central (NCDC) IDSR collation across all tenants, rolled up the gov
    hierarchy to national (super-admin)."""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        weeks = _weeks(request)
        return _idsr_response(platform_idsr_report(weeks), request)


class CaseReportExportView(APIView):
    """Download the current tenant's case reports as CSV (respects date range)."""

    permission_classes = [IsTenantMember]

    def get(self, request):
        from .stats import apply_range

        reports = apply_range(CaseReport.objects.all(), *_range(request))
        return case_reports_csv(reports)
