from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsClinicalStaff,
    IsPatientRegistrar,
    IsTenantAdmin,
    IsTenantMember,
    sees_whole_tenant,
)

from apps.tenants.current import get_current_tenant

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
        "consultations": (m.Consultation, s.ConsultationSerializer),
        "prescriptions": (m.Prescription, s.PrescriptionSerializer),
    }


def visible_patients(user):
    """The patients `user` may read, inside the tenant already bound.

    A clinician sees the records they are actually working on: the patients
    they registered, plus any patient they have filed a record against. Roles
    that run the facility rather than a caseload (see sees_whole_tenant) keep
    the full registry.

    Unclaimed rows stay visible to the facility's own clinicians. registered_by
    is NULL for patients imported ahead of go-live and for those whose
    registering staff member has since left (the FK is SET_NULL), and a patient
    nobody can open is worse than one too many people can.

    An independent prescriber gets no such fallback: they are a visitor to the
    facility, not its staff, so they see the patients they registered or wrote
    for and nothing else in the registry.

    A caseload crosses facilities: a patient registered elsewhere whom this
    clinician has consulted is on their list. The unclaimed fallback does not
    — it is this facility's own backlog.

    ponytail: one OR'd query across the record types, all indexed on the FK.
    Materialize the patient ids into a join table only if a clinician ever
    accumulates enough records for this to show up in a query plan.
    """
    if sees_whole_tenant(user):
        return Patient.objects.all()
    scope = Q(registered_by=user)
    if not user.is_independent:
        scope |= Q(registered_by__isnull=True, tenant=get_current_tenant())
    for model, _serializer in _history_sources().values():
        accessor = model._meta.get_field("patient").remote_field.get_accessor_name()
        scope |= Q(**{f"{accessor}__reporter": user})
    return Patient.all_objects.filter(scope).distinct()


class PatientViewSet(viewsets.ModelViewSet):
    """The patient register. Clinical staff and the front desk only — this is
    the one endpoint that returns identifying data, so plain tenant members
    can't read it. Reception registers and finds patients; the clinical
    timeline (history) stays with clinical staff.

    The roster is this facility's; a search or a read by id reaches a patient
    registered at any facility, so one registration serves every one of them.
    Deleting and merging stay with the facility that registered the patient.
    """

    serializer_class = PatientSerializer
    permission_classes = [IsTenantMember, IsPatientRegistrar]
    # An independent prescriber reaches this one: you cannot prescribe to a
    # patient you cannot register or find. visible_patients narrows them to
    # their own caseload (see get_queryset), and every read is still logged.
    independent_ok = True
    filterset_fields = ("sex", "status", "region", "blood_group", "genotype",
                        "patient_type")
    # next_of_kin_phone is searchable too: a relative's number is often the
    # only one reception is given, and it is normalized to the same shape.
    search_fields = ("hospital_number", "first_name", "last_name", "other_names",
                     "phone", "next_of_kin_phone", "nhis_number")
    ordering_fields = ("last_name", "created_at", "date_of_birth")

    def get_queryset(self):
        # Re-run the tenant-scoped manager per request (frozen-queryset gotcha).
        user = self.request.user
        searched = bool(self.request.query_params.get("search", "").strip())
        roster = self.action == "list" and not searched
        # The caseload (visible_patients) is a roster, not a fence. Reception
        # registers the patient and the doctor consults them, so the file
        # cannot be on the doctor's list before they open it: a search — the
        # name or number of the person in front of them — and a read by id
        # reach anyone on the facility's register, and every read is logged.
        # The register is shared across facilities: a patient registered at
        # a hospital is found at the pharmacy down the road by the same search.
        # An independent prescriber is a visitor, not staff: they stay inside
        # their own caseload whatever they type, and get no roster at all.
        if user.is_independent:
            qs = Patient.objects.none() if roster else visible_patients(user)
        else:
            qs = visible_patients(user) if roster else Patient.all_objects.all()
        return qs.prefetch_related("chronic_conditions")

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        if self.action != "list" or "status" in self.request.query_params:
            return qs
        # Merged duplicates are tombstones: still reachable by id or by asking
        # for ?status=merged, but out of the way of everyday lists. A search
        # that lands on one — the number on an old card — answers with the
        # record it was merged into instead.
        if self.request.query_params.get("search", "").strip():
            qs = qs | queryset.filter(
                pk__in=qs.filter(merged_into__isnull=False).values("merged_into")
            )
        return qs.exclude(status=Patient.Status.MERGED)

    def perform_create(self, serializer):
        serializer.save(registered_by=self.request.user)

    def _must_be_ours(self, patient):
        """Deleting or merging a record is the registering facility's call."""
        if patient.tenant_id != getattr(self.request.tenant, "id", None):
            raise PermissionDenied(
                "This patient was registered at another facility."
            )

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
        self._must_be_ours(patient)
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
        self._must_be_ours(target)
        source_id = request.data.get("source")
        source = Patient.objects.filter(pk=source_id).first() if source_id else None
        if source is None:
            raise ValidationError({"source": "No such patient in this tenant."})
        if source.pk == target.pk:
            raise ValidationError({"source": "A patient can't merge into itself."})
        if target.merged_into_id or source.merged_into_id:
            raise ValidationError(
                {"source": "One of these records was already merged away — "
                           "merge into the record that survived."}
            )
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

    @action(detail=True, methods=["get"],
            permission_classes=[IsTenantMember, IsClinicalStaff])
    def history(self, request, pk=None):
        """Everything filed against this patient, grouped by record type.

        Deliberately the whole timeline, not just this clinician's entries or
        this facility's: the gate is get_object(), so they already had to be
        on the patient's care. A half-history is how a repeat prescription
        gets written over an allergy someone else recorded.

        ponytail: one query per record type (8), each indexed on the FK. Fold into a union only if a patient ever accumulates enough
        rows for it to matter — a clinical timeline doesn't.
        """
        patient = self.get_object()
        out = {}
        for key, (model, serializer_class) in _history_sources().items():
            rows = model.all_objects.filter(patient=patient)
            out[key] = serializer_class(rows, many=True).data
        out["counts"] = {k: len(v) for k, v in out.items()}
        self._log(PatientAccessLog.Action.HISTORY, patient=patient,
                  count=sum(out["counts"].values()))
        return Response(out)
