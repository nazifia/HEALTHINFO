import re

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import normalize_phone
from apps.accounts.permissions import (
    IsClinicalStaff,
    IsTenantAdmin,
    IsTenantMember,
    sees_whole_tenant,
)

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


def visible_patients(user):
    """The patients `user` may read, inside the tenant already bound.

    A clinician sees the records they are actually working on: the patients
    they registered, plus any patient they have filed a record against. Roles
    that run the facility rather than a caseload (see sees_whole_tenant) keep
    the full registry.

    Unclaimed rows stay visible to everyone clinical. registered_by is NULL for
    patients imported ahead of go-live and for those whose registering staff
    member has since left (the FK is SET_NULL), and a patient nobody can open
    is worse than one too many people can.

    ponytail: one OR'd query across the record types, all indexed on the FK.
    Materialize the patient ids into a join table only if a clinician ever
    accumulates enough records for this to show up in a query plan.
    """
    qs = Patient.objects.all()
    if sees_whole_tenant(user):
        return qs
    scope = Q(registered_by=user) | Q(registered_by__isnull=True)
    for model, _serializer in _history_sources().values():
        accessor = model._meta.get_field("patient").remote_field.get_accessor_name()
        scope |= Q(**{f"{accessor}__reporter": user})
    return qs.filter(scope).distinct()


# A query that is nothing but digits and the separators people type into a
# phone number: "0803 123 4567", "+234-803-123-4567", "(0803)1234567".
_NUMBER_QUERY = re.compile(r"[+(]?\d[\d\s()+-]{4,}")


class NumberAwareSearchFilter(filters.SearchFilter):
    """SearchFilter that folds a typed number onto the shape we store.

    Phone numbers are normalized on write (see normalize_phone): every one is
    held as local ``0XXXXXXXXXX``. Without this, "+2348031234567" and
    "0803-123-4567" match nothing, and the default term split turns a spaced
    number into three fragments that match by luck rather than by number.
    Hospital numbers are digits too, and normalize_phone leaves them alone —
    they start 0, 3 or 4, never 234.
    """

    def get_search_terms(self, request):
        raw = request.query_params.get(self.search_param, "").strip()
        if _NUMBER_QUERY.fullmatch(raw):
            return [normalize_phone(raw)]
        return super().get_search_terms(request)


class PatientViewSet(viewsets.ModelViewSet):
    """Tenant-scoped patient registry. Clinical staff only — this is the one
    endpoint that returns identifying data, so plain tenant members can't read it.
    """

    serializer_class = PatientSerializer
    permission_classes = [IsTenantMember, IsClinicalStaff]
    filterset_fields = ("sex", "status", "region", "blood_group", "genotype",
                        "patient_type")
    # next_of_kin_phone is searchable too: a relative's number is often the
    # only one reception is given, and it is normalized to the same shape.
    search_fields = ("hospital_number", "first_name", "last_name", "other_names",
                     "phone", "next_of_kin_phone", "nhis_number")
    filter_backends = (DjangoFilterBackend, NumberAwareSearchFilter,
                       filters.OrderingFilter)
    ordering_fields = ("last_name", "created_at", "date_of_birth")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        qs = visible_patients(self.request.user).prefetch_related(
            "chronic_conditions"
        )
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

        Deliberately the whole timeline, not just this clinician's entries: the
        gate is get_object(), so they already had to be on the patient's care.
        A half-history is how a repeat prescription gets written over an
        allergy someone else recorded.

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
