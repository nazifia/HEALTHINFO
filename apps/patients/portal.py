"""The patient's own view of their record.

Every staff endpoint answers "which of my patients"; this one answers "my
record". The difference is where the patient id comes from: here it is never
sent by the caller, only read off the signed-in account (``Patient.user``), so
a portal account can only ever reach the one record it is linked to. Nothing
here writes — a patient reads their details, their history, what was
prescribed, and where to go and get it.

Reads leave the same audit trail staff reads do (see PatientAccessLog): "the
patient themselves" is an answer that log should be able to give.
"""
from math import asin, cos, radians, sin, sqrt

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.branches.models import Branch
from apps.branches.serializers import BranchSerializer
from apps.tenants.models import Tenant

from .models import Patient, PatientAccessLog
from .serializers import PatientSerializer
from .views import _history_sources

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
        return patient

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
    @action(detail=False, methods=["get"])
    def me(self, request):
        """The patient's own details."""
        patient = self._record()
        self._log(patient, PatientAccessLog.Action.RETRIEVE, 1)
        return Response(PatientSerializer(patient).data)

    @action(detail=False, methods=["get"])
    def history(self, request):
        """The whole medical history, grouped by record type.

        Same shape and same sources as the clinician's timeline (see
        PatientViewSet.history), so one client renderer serves both.
        """
        patient = self._record()
        out = {}
        for key, (model, serializer_class) in _history_sources().items():
            rows = model.all_objects.filter(patient=patient)
            out[key] = serializer_class(rows, many=True).data
        out["counts"] = {k: len(v) for k, v in out.items()}
        self._log(patient, PatientAccessLog.Action.HISTORY,
                  sum(out["counts"].values()))
        return Response(out)

    @action(detail=False, methods=["get"])
    def medications(self, request):
        """Everything prescribed to this patient, newest first.

        One list whichever route the drug came down: an order a clinician wrote
        and a line off a counter script both land in ``analytics.Prescription``
        (see apps.analytics.capture), so reading that is reading both.
        ``?status=`` narrows to one state — what is still to be collected is
        ``?status=prescribed``.
        """
        from apps.analytics.models import Prescription
        from apps.analytics.serializers import PrescriptionSerializer

        patient = self._record()
        rows = Prescription.all_objects.filter(
            patient=patient
        ).select_related("medication")
        status = request.query_params.get("status")
        if status:
            rows = rows.filter(status=status)
        data = PrescriptionSerializer(rows, many=True).data
        self._log(patient, PatientAccessLog.Action.HISTORY, len(data))
        return Response(data)

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
