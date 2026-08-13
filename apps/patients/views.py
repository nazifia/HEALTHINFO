from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
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
    filterset_fields = ("sex", "status", "region", "blood_group", "genotype",
                        "patient_type")
    search_fields = ("hospital_number", "first_name", "last_name", "other_names",
                     "phone", "nhis_number")
    ordering_fields = ("last_name", "created_at", "date_of_birth")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        qs = Patient.objects.all().prefetch_related("chronic_conditions")
        # Merged duplicates are tombstones: still reachable by id or by asking
        # for ?status=merged, but out of the way of everyday lists and searches.
        if self.action == "list" and "status" not in self.request.query_params:
            qs = qs.exclude(status=Patient.Status.MERGED)
        return qs

    def perform_create(self, serializer):
        serializer.save(registered_by=self.request.user)

    # --- read audit ------------------------------------------------------
    # Every read of identifying data is recorded. Deliberately fail-closed: if
    # the log write fails the read fails with it, so there is no way to read a
    # patient record without leaving a trace.
    def _log(self, action_name, patient=None, count=0, query=None):
        PatientAccessLog.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            patient=patient,
            action=action_name,
            query=(query if query is not None
                   else self.request.query_params.get("search", ""))[:255],
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

    def destroy(self, request, *args, **kwargs):
        patient = self.get_object()
        # A patient with clinical records can't be deleted: the reports survive
        # (SET_NULL) but silently lose the link, which quietly corrupts every
        # history and rollup that used it. Retire or merge the record instead.
        counts = patient.clinical_record_counts()
        if counts:
            raise ValidationError({
                "detail": "This patient has clinical records on file. Set the "
                          "status to inactive, or merge into the record that "
                          "should survive.",
                "clinical_records": counts,
            })
        # Logged before the row goes, and the identity goes in `query`: the FK
        # is SET_NULL, so afterwards nothing else says which patient this was.
        self._log(PatientAccessLog.Action.DELETE, patient=patient, count=1,
                  query=f"{patient.hospital_number} {patient.full_name}")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"],
            permission_classes=[IsTenantMember, IsTenantAdmin])
    def merge(self, request, pk=None):
        """Absorb a duplicate into this record: ``{"source": <patient id>}``.

        This record survives; the duplicate becomes a tombstone pointing here.
        Tenant admins only — it rewrites clinical history, and the staff who
        create duplicates shouldn't be the ones resolving them unreviewed.
        """
        target = self.get_object()
        source_id = request.data.get("source")
        source = Patient.objects.filter(pk=source_id).first() if source_id else None
        if source is None:
            raise ValidationError({"source": "No such patient in this tenant."})
        if source.pk == target.pk:
            raise ValidationError({"source": "A patient can't merge into itself."})
        moved = target.merge_from(source)
        self._log(PatientAccessLog.Action.MERGE, patient=target,
                  count=sum(moved.values()),
                  query=f"merged {source.hospital_number} into "
                        f"{target.hospital_number}")
        return Response({
            "patient": PatientSerializer(target).data,
            "merged": PatientSerializer(source).data,
            "moved": moved,
        })

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
