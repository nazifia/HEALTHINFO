"""Knowledge-graph traversal APIs (tenant-scoped via the model managers).

Edges modelled so far:
  Disease  -- symptoms -->     Symptom
  Disease  -- medications -->  Medication
  Disease  -- procedures -->   Procedure
  Disease  -- lab_tests -->    LabTest
  Disease  -- specialties -->  Specialty
  Disease  -- articles -->     Article
  Medication -- interactions --> Medication   (DrugInteraction)
  Medication -- articles -->   Article
  Procedure / Specialty have their own neighbour views below.
"""
from django.db.models import Q
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsTenantMember

from .models import Disease, DrugInteraction, Medication, Procedure, Specialty


def _public(request):
    """True if the caller only ever sees published content (PUBLIC role)."""
    user = request.user
    return user.is_authenticated and getattr(user, "role", None) == Role.PUBLIC


def _pub(request, qs):
    """Hide unpublished from PUBLIC users; staff see all statuses.

    Mirrors WorkflowViewSetMixin.get_queryset so the graph can't leak drafts
    the catalog list/search endpoints already hide. Only for status-bearing
    models (Disease/Medication/Procedure/LabTest/Article); Symptom, Specialty
    and DrugInteraction have no workflow.
    """
    return qs.filter(status="published") if _public(request) else qs
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


class DiseaseGraphView(APIView):
    """Neighbours of a disease + 1-hop: diseases sharing a symptom."""

    permission_classes = [IsTenantMember]

    def get(self, request, pk):
        disease = get_object_or_404(_pub(request, Disease.objects.all()), pk=pk)
        symptoms = disease.symptoms.all()
        related = (
            _pub(request, Disease.objects.filter(symptoms__in=symptoms))
            .exclude(pk=disease.pk)
            .distinct()
        )
        return Response(
            {
                "disease": DiseaseSerializer(disease).data,
                "symptoms": SymptomSerializer(symptoms, many=True).data,
                "medications": MedicationSerializer(
                    _pub(request, disease.medications.all()), many=True
                ).data,
                "procedures": ProcedureSerializer(
                    _pub(request, disease.procedures.all()), many=True
                ).data,
                "lab_tests": LabTestSerializer(
                    _pub(request, disease.lab_tests.all()), many=True
                ).data,
                "specialties": SpecialtySerializer(
                    disease.specialties.all(), many=True
                ).data,
                "articles": ArticleSerializer(
                    _pub(request, disease.articles.all()), many=True
                ).data,
                "related_diseases": DiseaseSerializer(related, many=True).data,
            }
        )


class MedicationGraphView(APIView):
    """Neighbours of a medication: interactions + diseases it treats."""

    permission_classes = [IsTenantMember]

    def get(self, request, pk):
        med = get_object_or_404(_pub(request, Medication.objects.all()), pk=pk)
        interactions = DrugInteraction.objects.filter(
            Q(medication_a=med) | Q(medication_b=med)
        )
        return Response(
            {
                "medication": MedicationSerializer(med).data,
                "interactions": DrugInteractionSerializer(
                    interactions, many=True
                ).data,
                "treats_diseases": DiseaseSerializer(
                    _pub(request, med.diseases.all()), many=True
                ).data,
                "articles": ArticleSerializer(
                    _pub(request, med.articles.all()), many=True
                ).data,
            }
        )


class ProcedureGraphView(APIView):
    """Neighbours of a procedure: diseases it applies to."""

    permission_classes = [IsTenantMember]

    def get(self, request, pk):
        proc = get_object_or_404(_pub(request, Procedure.objects.all()), pk=pk)
        return Response(
            {
                "procedure": ProcedureSerializer(proc).data,
                "diseases": DiseaseSerializer(
                    _pub(request, proc.diseases.all()), many=True
                ).data,
            }
        )


class SpecialtyGraphView(APIView):
    """Neighbours of a specialty: diseases under it."""

    permission_classes = [IsTenantMember]

    def get(self, request, pk):
        spec = get_object_or_404(Specialty.objects.all(), pk=pk)
        return Response(
            {
                "specialty": SpecialtySerializer(spec).data,
                "diseases": DiseaseSerializer(
                    _pub(request, spec.diseases.all()), many=True
                ).data,
            }
        )
