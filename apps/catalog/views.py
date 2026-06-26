import operator
from functools import reduce

from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsTenantMember, ReadOnlyOrWriteRole
from apps.analytics.tracking import ViewTrackingMixin, track
from apps.governance.mixins import WorkflowViewSetMixin

from .models import (
    Article,
    Disease,
    DrugInteraction,
    LabTest,
    Medication,
    Procedure,
    Specialty,
    Symptom,
)
from .serializers import (
    ArticleSerializer,
    DiseaseSerializer,
    DrugInteractionSerializer,
    LabTestSerializer,
    MedicationSerializer,
    ProcedureSerializer,
    SpecialtySerializer,
    SymptomSerializer,
)

DISCLAIMER = "This information is educational only and not medical advice."


class TenantQuerysetMixin:
    """Re-run the manager per request.

    DRF freezes `self.queryset` at import; with the tenant-scoped manager that
    captures an empty queryset (no tenant bound at import), so lists always come
    back empty. Re-evaluating the manager binds the current request's tenant.
    """

    def get_queryset(self):
        return self.queryset.model.objects.all()


class DiseaseViewSet(
    ViewTrackingMixin, WorkflowViewSetMixin, TenantQuerysetMixin, viewsets.ModelViewSet
):
    # Manager is already tenant-scoped, so this never leaks across tenants.
    analytics_object_type = "disease"
    queryset = Disease.objects.all()
    serializer_class = DiseaseSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("status", "icd10_code", "notifiable")
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    ordering = ("name",)  # deterministic pagination (else UnorderedObjectListWarning)


class MedicationViewSet(
    ViewTrackingMixin, WorkflowViewSetMixin, TenantQuerysetMixin, viewsets.ModelViewSet
):
    analytics_object_type = "medication"
    queryset = Medication.objects.all()
    serializer_class = MedicationSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("status", "drug_class")
    search_fields = ("generic_name", "brand_name", "description")
    ordering_fields = ("generic_name", "created_at")
    ordering = ("generic_name",)


class SymptomViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Symptom.objects.all()
    serializer_class = SymptomSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    search_fields = ("name", "description")
    ordering_fields = ("name", "severity_level")
    ordering = ("name",)


class DrugInteractionViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = DrugInteraction.objects.all()
    serializer_class = DrugInteractionSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("severity", "medication_a", "medication_b")
    ordering = ("id",)


class SpecialtyViewSet(TenantQuerysetMixin, viewsets.ModelViewSet):
    queryset = Specialty.objects.all()
    serializer_class = SpecialtySerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    ordering = ("name",)


class ProcedureViewSet(
    ViewTrackingMixin, WorkflowViewSetMixin, TenantQuerysetMixin, viewsets.ModelViewSet
):
    analytics_object_type = "procedure"
    queryset = Procedure.objects.all()
    serializer_class = ProcedureSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("status",)
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    ordering = ("name",)


class LabTestViewSet(
    ViewTrackingMixin, WorkflowViewSetMixin, TenantQuerysetMixin, viewsets.ModelViewSet
):
    analytics_object_type = "lab_test"
    queryset = LabTest.objects.all()
    serializer_class = LabTestSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("status",)
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at")
    ordering = ("name",)


class ArticleViewSet(
    ViewTrackingMixin, WorkflowViewSetMixin, TenantQuerysetMixin, viewsets.ModelViewSet
):
    analytics_object_type = "article"
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsTenantMember, ReadOnlyOrWriteRole]
    filterset_fields = ("status",)
    search_fields = ("title", "summary", "body")
    ordering_fields = ("title", "created_at")
    ordering = ("title",)


class SearchView(APIView):
    """Substring search across published catalog content (tenant-scoped).

    PharmApp-style: case-insensitive `icontains` OR'd across each model's text
    fields. Matches partial words ("diab" -> "diabetes"), works on every backend
    (sqlite/mysql/postgres), no full-text config to keep in sync.

    Covers diseases, medications, procedures, lab tests, articles. Symptom and
    Specialty are reference taxonomies (no workflow/status) and stay out of search.
    """

    permission_classes = [IsTenantMember]
    throttle_scope = "search"

    # model qs -> ordering field + fields searched with icontains.
    _TARGETS = {
        "diseases": ("name", ("name", "description", "causes", "treatment")),
        "medications": ("generic_name", ("generic_name", "brand_name", "description", "indications")),
        "procedures": ("name", ("name", "description", "indications")),
        "lab_tests": ("name", ("name", "description", "purpose")),
        "articles": ("title", ("title", "summary", "body")),
    }

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        # PharmApp guard: ignore 1-char noise, return empty result set (not 400).
        if len(q) < 2:
            return Response({"detail": "q must be at least 2 characters"}, status=400)
        try:
            limit = min(max(int(request.query_params.get("limit", 20)), 1), 50)
        except (TypeError, ValueError):
            limit = 20

        querysets = {
            "diseases": Disease.objects.filter(status="published"),
            "medications": Medication.objects.filter(status="published"),
            "procedures": Procedure.objects.filter(status="published"),
            "lab_tests": LabTest.objects.filter(status="published"),
            "articles": Article.objects.filter(status="published"),
        }
        serializers = {
            "diseases": DiseaseSerializer,
            "medications": MedicationSerializer,
            "procedures": ProcedureSerializer,
            "lab_tests": LabTestSerializer,
            "articles": ArticleSerializer,
        }

        results, total = {}, 0
        for key, qs in querysets.items():
            order_field, fields = self._TARGETS[key]
            hits = self._search(qs, q, fields, order_field, limit)
            total += len(hits)
            results[key] = serializers[key](hits, many=True).data

        track(request, "search", query=q[:500], result_count=total)
        return Response({"disclaimer": DISCLAIMER, "total": total, **results})

    @staticmethod
    def _search(qs, q, fields, order_field, limit):
        # icontains OR across fields. LIKE '%q%' can't use a btree index (seq
        # scan); fine at catalog scale. ponytail: add trigram GIN if it gets slow.
        predicate = reduce(operator.or_, (Q(**{f"{f}__icontains": q}) for f in fields))
        return qs.filter(predicate).order_by(order_field)[:limit]


class InteractionCheckView(APIView):
    """Given a set of medication ids, return every known interaction among them.

    The clinical question: "patient is on these N drugs — any conflicts?" Pairs
    are matched in either column order. Tenant-scoped manager keeps it isolated.
    """

    permission_classes = [IsTenantMember]

    def post(self, request):
        ids = request.data.get("medication_ids") or []
        if not isinstance(ids, list) or len(ids) < 2:
            return Response(
                {"detail": "medication_ids must be a list of at least 2 ids"},
                status=400,
            )
        try:
            ids = {int(i) for i in ids}
        except (TypeError, ValueError):
            return Response(
                {"detail": "medication_ids must be a list of integer ids"},
                status=400,
            )
        hits = DrugInteraction.objects.filter(
            medication_a_id__in=ids, medication_b_id__in=ids
        )
        return Response({
            "disclaimer": DISCLAIMER,
            "checked": sorted(ids),
            "interactions": DrugInteractionSerializer(hits, many=True).data,
        })


class DifferentialView(APIView):
    """Given symptom ids, rank published diseases by how many match.

    Decision-support, not diagnosis — hence the disclaimer and the `matched`
    count so a clinician sees the strength of each suggestion.
    """

    permission_classes = [IsTenantMember]

    def post(self, request):
        ids = request.data.get("symptom_ids") or []
        if not isinstance(ids, list) or not ids:
            return Response(
                {"detail": "symptom_ids must be a non-empty list"}, status=400
            )
        try:
            ids = {int(i) for i in ids}
        except (TypeError, ValueError):
            return Response(
                {"detail": "symptom_ids must be a list of integer ids"}, status=400
            )
        ranked = (
            Disease.objects.filter(status="published", symptoms__in=ids)
            .annotate(matched=Count("symptoms", filter=Q(symptoms__in=ids), distinct=True))
            .order_by("-matched", "name")[:20]
        )
        results = [
            {"id": d.id, "name": d.name, "icd10_code": d.icd10_code, "matched": d.matched}
            for d in ranked
        ]
        return Response({
            "disclaimer": DISCLAIMER,
            "symptom_count": len(ids),
            "results": results,
        })


class NotifiableReportView(APIView):
    """Cases of legally-notifiable diseases in the window — the regulator report.

    Filters CaseReport to diseases flagged ``notifiable`` so a tenant can pull
    exactly what must be sent to public-health authorities. Date range via
    ?from=&to=. Add ?format=csv for a downloadable file.
    """

    permission_classes = [IsTenantMember]

    def get(self, request):
        from django.utils.dateparse import parse_date

        from apps.analytics.export import csv_response
        from apps.analytics.models import CaseReport

        qs = CaseReport.objects.filter(disease__notifiable=True)
        start = parse_date(request.query_params.get("from", "") or "")
        end = parse_date(request.query_params.get("to", "") or "")
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)
        cols = (
            "id", "created_at", "disease__name", "disease__icd10_code",
            "severity", "outcome", "patient_age_group", "patient_sex", "region",
        )
        if request.query_params.get("format") == "csv":
            return csv_response("notifiable_cases.csv", cols, qs.values_list(*cols).order_by("-created_at"))
        rows = list(qs.values(*cols).order_by("-created_at"))
        return Response({"count": len(rows), "cases": rows})
