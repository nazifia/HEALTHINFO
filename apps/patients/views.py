from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsClinicalStaff, IsTenantAdmin, IsTenantMember

from .models import Patient, PatientAccessLog
from .serializers import PatientAccessLogSerializer, PatientSerializer

# Record types shown on a patient's timeline: response key -> (model, serializer).
# Every one of these carries the optional `patient` FK (see
# apps.analytics.models.PatientLinkedModel), so the lookup is the same for all.
def _history_sources():
    """Imported lazily — analytics imports patients' model via a string FK, and
    keeping this out of module scope avoids an import cycle at app load."""
    from apps.analytics import models as m
    from apps.analytics import serializers as s

    return {
        "case_reports": (m.CaseReport, s.CaseReportSerializer),
        "adverse_reactions": (m.AdverseDrugReaction, s.AdverseDrugReactionSerializer),
        "lab_results": (m.LabResult, s.LabResultSerializer),
        "immunizations": (m.Immunization, s.ImmunizationSerializer),
        "vital_events": (m.VitalEvent, s.VitalEventSerializer),
        "chw_reports": (m.CommunityHealthReport, s.CommunityHealthReportSerializer),
        "insurance_claims": (m.InsuranceClaim, s.InsuranceClaimSerializer),
        "appointments": (m.Appointment, s.AppointmentSerializer),
    }


class PatientViewSet(viewsets.ModelViewSet):
    """Tenant-scoped patient registry. Clinical staff only — this is the one
    endpoint that returns identifying data, so plain tenant members can't read it.
    """

    serializer_class = PatientSerializer
    permission_classes = [IsTenantMember, IsClinicalStaff]
    filterset_fields = ("sex", "status", "region", "blood_group", "genotype")
    search_fields = ("hospital_number", "first_name", "last_name", "other_names",
                     "phone", "nhis_number")
    ordering_fields = ("last_name", "created_at", "date_of_birth")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        return Patient.objects.all().prefetch_related("chronic_conditions")

    def perform_create(self, serializer):
        serializer.save(registered_by=self.request.user)

    # --- read audit ------------------------------------------------------
    # Every read of identifying data is recorded. Deliberately fail-closed: if
    # the log write fails the read fails with it, so there is no way to read a
    # patient record without leaving a trace.
    def _log(self, action_name, patient=None, count=0):
        PatientAccessLog.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            patient=patient,
            action=action_name,
            query=self.request.query_params.get("search", "")[:255],
            result_count=count,
        )

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        body = response.data
        count = body.get("count", 0) if isinstance(body, dict) else len(body)
        self._log(PatientAccessLog.Action.LIST, count=count)
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._log(PatientAccessLog.Action.RETRIEVE, patient=self.get_object(),
                  count=1)
        return response

    @action(detail=False, url_path="access-log",
            permission_classes=[IsTenantMember, IsTenantAdmin])
    def access_log(self, request):
        """Who read what, newest first — tenant admins only.

        ``?patient=<id>`` narrows it to one record's trail, ``?action=`` to one
        kind of read. Clinical staff generate this log, so they can't be the
        ones to audit it.
        """
        rows = PatientAccessLog.objects.select_related("user", "patient")
        patient_id = request.query_params.get("patient")
        if patient_id:
            rows = rows.filter(patient_id=patient_id)
        action_filter = request.query_params.get("action")
        if action_filter:
            rows = rows.filter(action=action_filter)
        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(
                PatientAccessLogSerializer(page, many=True).data
            )
        return Response(PatientAccessLogSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        """Everything filed against this patient, grouped by record type.

        ponytail: one query per record type (8), each tenant-scoped and indexed
        on the FK. Fold into a union only if a patient ever accumulates enough
        rows for it to matter — a clinical timeline doesn't.
        """
        patient = self.get_object()
        out = {}
        for key, (model, serializer_class) in _history_sources().items():
            rows = model.objects.filter(patient=patient)
            out[key] = serializer_class(rows, many=True).data
        out["counts"] = {k: len(v) for k, v in out.items()}
        self._log(PatientAccessLog.Action.HISTORY, patient=patient,
                  count=sum(out["counts"].values()))
        return Response(out)
