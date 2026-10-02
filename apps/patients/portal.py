"""The patient's own view of their record.

Every staff endpoint answers "which of my patients"; this one answers "my
record". The difference is where the patient id comes from: here it is never
sent by the caller, only read off the signed-in account (``Patient.user``), so
a portal account can only ever reach the one record it is linked to. It is
deliberately narrow: a patient reads their own details, the diagnoses made for
them, the drugs the pharmacy actually handed over, and where to go and get
more. The only personal fields they can change are how to reach them — address
and next of kin.

The rest of the clinical timeline — labs, claims, consultation notes — is the
facility's working record and is not served here. A patient asks the facility
that wrote it for it.

Reads leave the same audit trail staff reads do (see PatientAccessLog): "the
patient themselves" is an answer that log should be able to give.
"""
from math import asin, cos, radians, sin, sqrt

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.branches.models import Branch
from apps.branches.serializers import BranchSerializer
from apps.tenants.models import Tenant

from .models import Patient, PatientAccessLog
from .serializers import PatientSerializer

EARTH_RADIUS_KM = 6371.0

# How many pharmacies the nearby list returns when the client doesn't say.
DEFAULT_PHARMACY_LIMIT = 20
MAX_PHARMACY_LIMIT = 100


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points, in kilometres.

    ponytail: spherical earth, good to about half a percent — plenty to sort
    shops by which one is nearer. Move to PostGIS/GeoDjango only if a distance
    ever has to be accurate in metres, or the branch list outgrows a full scan.
    """
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (sin(dlat / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2)
    return round(2 * EARTH_RADIUS_KM * asin(sqrt(a)), 2)


def _coords(request):
    """The caller's position from ?lat=&lng=, or (None, None) if not shared.

    Sharing a location is optional: without one the list still answers, it
    just cannot order itself by distance.
    """
    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    if lat in (None, "") and lng in (None, ""):
        return None, None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValidationError({"lat": "Send lat and lng as decimal degrees."})
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError({"lat": "Those coordinates are off the map."})
    return lat, lng


def _limit(request):
    """How many rows the nearby list may return."""
    raw = request.query_params.get("limit")
    if not raw:
        return DEFAULT_PHARMACY_LIMIT
    try:
        limit = int(raw)
    except ValueError:
        raise ValidationError({"limit": "Send a whole number."})
    return max(1, min(limit, MAX_PHARMACY_LIMIT))


class PatientPortalViewSet(viewsets.ViewSet):
    """Read-only endpoints a patient uses on their own record.

    Sign-in is the ordinary one (``/api/auth/token/`` with their phone); what
    makes an account a patient account is being linked to a Patient row. An
    account with no link is refused on everything personal here, so the client
    can tell "not a patient" apart from "no records yet".
    """

    permission_classes = [IsAuthenticated]

    # --- the record this account is ---------------------------------------
    def _record(self):
        """The signed-in patient's row.

        Off ``all_objects`` on purpose: the row carries its own tenant and an
        account links to exactly one record, so this needs no tenant header
        from the client — a patient app talks to the API, not to the
        facility's host.
        """
        patient = Patient.all_objects.filter(user=self.request.user).first()
        if patient is None:
            raise PermissionDenied(
                "This account is not linked to a patient record. Ask the "
                "facility that registered you to link it."
            )
        # Linked to a duplicate that was since merged away: the records are
        # on the survivor now (see Patient.merge_from).
        return patient.merged_into or patient

    def _log(self, patient, action_name, count):
        # Tenant stamped from the patient, not from the request: a portal
        # client sends no tenant header, and an unstamped row is one the
        # facility's audit would never list.
        PatientAccessLog.all_objects.create(
            tenant_id=patient.tenant_id, user=self.request.user,
            patient=patient, action=action_name, query="portal",
            result_count=count,
        )

    # --- personal reads ----------------------------------------------------
    # What a patient may correct about themselves: where they live and who to
    # call. Name, sex, date of birth and the clinical fields are the facility's
    # to change, against the evidence in front of it.
    SELF_EDITABLE = ("address", "next_of_kin_name", "next_of_kin_phone",
                     "next_of_kin_relationship")

    @action(detail=False, methods=["get", "patch"])
    def me(self, request):
        """The patient's own details; PATCH changes the SELF_EDITABLE ones."""
        patient = self._record()
        if request.method == "PATCH":
            refused = set(request.data) - set(self.SELF_EDITABLE)
            if refused:
                raise ValidationError({f: "Ask the facility to change this."
                                       for f in sorted(refused)})
            ser = PatientSerializer(patient, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        self._log(patient, PatientAccessLog.Action.RETRIEVE, 1)
        return Response(PatientSerializer(patient).data)

    @action(detail=False, methods=["get"])
    def diagnoses(self, request):
        """What this patient was diagnosed with, where and when, newest first.

        The diagnosis only — disease, severity, outcome, facility — not the
        case's notes, which are the clinician's working record.
        """
        from apps.analytics.models import CaseReport

        patient = self._record()
        rows = CaseReport.all_objects.filter(
            patient=patient, disease__isnull=False
        ).select_related("disease", "tenant")
        data = [{
            "id": c.id, "date": c.created_at.date(),
            "disease_name": c.disease.name, "severity": c.severity,
            "outcome": c.outcome, "facility": c.tenant.name if c.tenant_id else "",
        } for c in rows]
        self._log(patient, PatientAccessLog.Action.HISTORY, len(data))
        return Response(data)

    @action(detail=False, methods=["get"])
    def medications(self, request):
        """The drugs this patient has actually been given, newest first.

        Dispensed only. An order a clinician has written but the pharmacy has
        not filled is not yet a fact about the patient — it can still be
        changed or cancelled at the counter — so the portal shows a drug from
        the moment it is handed over, not from the moment it is written. A
        partly filled script counts: some of it is in the patient's hands.

        One list whichever route the drug came down: an order a clinician wrote
        and a line off a counter script both land in ``analytics.Prescription``
        (see apps.analytics.capture), so reading that is reading both. The
        caller chooses no status, and nothing undispensed is served anywhere
        on the portal: an unfilled order stays with the facility.
        """
        from apps.analytics.models import Prescription
        from apps.analytics.serializers import PrescriptionSerializer

        patient = self._record()
        rows = Prescription.all_objects.filter(
            patient=patient,
            status__in=(Prescription.Status.DISPENSED,
                        Prescription.Status.PARTIAL),
        ).select_related("medication")
        data = list(PrescriptionSerializer(rows, many=True).data)
        data += self._uncatalogued(patient)
        self._log(patient, PatientAccessLog.Action.HISTORY, len(data))
        return Response(data)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Drugs ordered for this patient and not yet handed over.

        Kept off ``medications`` on purpose (an order can still change at the
        counter); served on its own so the portal can alert, not list it as
        something the patient has.
        """
        from apps.analytics.models import Prescription

        patient = self._record()
        rows = Prescription.all_objects.filter(
            patient=patient, status=Prescription.Status.PRESCRIBED,
        ).select_related("medication")
        return Response([{
            "id": r.id, "medication_name": r.medication.generic_name,
            "dose": r.dose, "frequency": r.frequency,
            "duration_days": r.duration_days, "created_at": r.created_at,
        } for r in rows])

    @staticmethod
    def _uncatalogued(patient):
        """Items handed over at a counter that match no catalog drug.

        capture_dispense files only catalog drugs, so these have no Prescription
        row; they are read straight off the dispensing log under the item's own
        name, with ``medication`` null (nothing to look up a pharmacy for).
        ponytail: matched per row, fine at one patient's volume.
        """
        from apps.analytics.capture import medication_for
        from apps.pos.models import DispensingLog, Sale

        logs = DispensingLog.all_objects.filter(
            sale__patient=patient, status=DispensingLog.Status.DISPENSED,
        ).exclude(sale__status=Sale.Status.CANCELLED).select_related("item")
        return [{
            "id": f"dispense-{log.pk}", "medication": None,
            "medication_name": log.name, "dose": "", "frequency": "",
            "duration_days": None, "status": "dispensed",
            "created_at": log.created_at,
        } for log in logs if medication_for(log.tenant_id, log.item, log.name) is None]

    # --- the people on my card ---------------------------------------------
    @action(detail=False, methods=["get"])
    def enrollments(self, request):
        """The schemes this patient is a member of - what a dependent goes under."""
        from apps.pharmacy.models import HmoEnrollment
        from apps.pharmacy.serializers import HmoEnrollmentSerializer

        patient = self._record()
        rows = HmoEnrollment.all_objects.filter(
            patient=patient, is_active=True).select_related("hmo")
        return Response(HmoEnrollmentSerializer(rows, many=True).data)

    @action(detail=False, methods=["get", "post"])
    def dependents(self, request):
        """The people the principal has asked to have covered, and asking.

        POST names one: ``enrollment`` (one of the caller's own memberships;
        left out, the only one they have), ``full_name``, ``relationship``,
        optional ``sex``, ``date_of_birth``, ``phone``. It lands as pending;
        the scheme's own seat approves it (see SchemeDependentViewSet). The
        row is stamped with the enrollment's tenant, the way the audit row is:
        a portal call carries no tenant header.
        """
        from apps.pharmacy.models import HmoEnrollment, SchemeDependent
        from apps.pharmacy.serializers import SchemeDependentSerializer

        patient = self._record()
        mine = HmoEnrollment.all_objects.filter(patient=patient)
        if request.method == "GET":
            rows = SchemeDependent.all_objects.filter(
                enrollment__in=mine
            ).select_related("enrollment", "enrollment__hmo",
                             "enrollment__patient", "decided_by")
            return Response(SchemeDependentSerializer(rows, many=True).data)

        wanted = request.data.get("enrollment")
        active = mine.filter(is_active=True)
        enrollment = (active.filter(pk=wanted).first() if wanted
                      else active.first() if active.count() == 1 else None)
        if enrollment is None:
            raise ValidationError({"enrollment": "Pick which of your scheme "
                                   "memberships this dependent goes under."})
        ser = SchemeDependentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        dep = ser.save(tenant_id=enrollment.tenant_id, enrollment=enrollment)
        return Response(SchemeDependentSerializer(dep).data,
                        status=status.HTTP_201_CREATED)

    # --- where to fill it --------------------------------------------------
    @action(detail=False, methods=["get"])
    def pharmacies(self, request):
        """Dispensing sites, nearest first for a caller who shares ?lat=&lng=.

        Deliberately not scoped to the patient's own facility: the point of the
        list is where a drug can actually be got, and the pharmacy round the
        corner belongs to somebody else. What it gives out is what a shop puts
        on its signboard — name, address, phone, where it is — and only for
        live organizations.

        ``?medication=<catalog medication id>`` narrows it to sites with that
        drug on the shelf; ``?limit=`` caps the list (default 20, max 100).

        ponytail: distances computed in Python over every geocoded branch. Fine
        for a national list in the hundreds; add a bounding-box prefilter (or
        PostGIS) when it is in the tens of thousands.
        """
        lat, lng = _coords(request)
        branches = Branch.all_objects.filter(
            is_active=True,
            tenant__status=Tenant.Status.ACTIVE,
            tenant__subscription_status=Tenant.SubscriptionStatus.APPROVED,
        ).select_related("tenant")
        medication = request.query_params.get("medication")
        if medication:
            # In stock means a batch with something left on it, not merely an
            # item on the price list.
            branches = branches.filter(
                items__medication_id=medication, items__batches__quantity__gt=0
            ).distinct()
        rows = []
        for branch in branches:
            row = BranchSerializer(branch).data
            row["pharmacy"] = branch.tenant.name if branch.tenant_id else ""
            located = branch.latitude is not None and branch.longitude is not None
            row["distance_km"] = (
                haversine_km(lat, lng, float(branch.latitude),
                             float(branch.longitude))
                if located and lat is not None else None
            )
            rows.append(row)
        # Sites nobody has geocoded sort last: they can still be phoned, but
        # nothing can be said about how far away they are.
        rows.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0))
        return Response(rows[:_limit(request)])
