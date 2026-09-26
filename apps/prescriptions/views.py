"""Prescriptions API: scripts filled at the counter."""
import django_filters
from django.db import transaction
from django.db.models import Count, Q
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import normalize_phone
from apps.analytics.models import Prescription as DrugOrder
from apps.analytics.serializers import PrescriptionSerializer as DrugOrderSerializer
from apps.inventory.views import PharmacyViewSet
from apps.patients.models import (
    Patient,
    PatientAccessLog,
    number_search_term,
    patients_by_number,
    with_survivors,
)
from config.responses import success

from .models import Prescription, PrescriptionItem
from .serializers import (
    OutsideOrderSerializer,
    OutsideScriptSerializer,
    PrescriptionSerializer,
)

# What a dispenser can still act on. Cancelled and fully dispensed scripts are
# history; these two are work.
OPEN = (Prescription.Status.PENDING, Prescription.Status.PARTIAL)
OPEN_ORDERS = (DrugOrder.Status.PRESCRIBED, DrugOrder.Status.PARTIAL)


def _is_true(value):
    return (value or "").strip().lower() in ("1", "true", "yes")


class PrescriptionFilter(django_filters.FilterSet):
    """Script filters, plus the one the counter actually asks for.

    "Is this still owed?" spans two states, so ``?status=undispensed`` and
    ``?undispensed=1`` both mean pending or part-filled. Without the alias a
    client has to ask twice and stitch the pages together.
    """

    status = django_filters.CharFilter(method="filter_status")
    undispensed = django_filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Prescription
        fields = ("status", "source", "customer", "patient", "branch")

    def filter_status(self, qs, name, value):
        if value == "undispensed":
            return qs.filter(status__in=OPEN)
        return qs.filter(status=value)

    def filter_open(self, qs, name, value):
        return qs.filter(status__in=OPEN) if value else qs


class PrescriptionViewSet(PharmacyViewSet):
    """Scripts presented at the counter and what has been filled off them."""

    model = Prescription
    serializer_class = PrescriptionSerializer
    filterset_class = PrescriptionFilter
    search_fields = ("customer_name", "customer_phone", "doctor_name",
                     "diagnosis")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return Prescription.objects.select_related(
            "customer", "branch"
        ).prefetch_related("lines")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, url_path="pending-count")
    def pending_count(self, request):
        """How much is still owed at the counter: ``{pending, partial, total}``.

        An aggregate, not a list: this is what a header badge reads on every
        screen, and it must not cost a page of scripts to answer.
        ``?branch=<id>`` scopes it to one counter.
        """
        qs = self.model.objects.filter(status__in=OPEN)
        branch = (request.query_params.get("branch") or "").strip()
        if branch.isdigit():
            qs = qs.filter(branch_id=int(branch))
        counts = qs.aggregate(
            pending=Count("id", filter=Q(status=Prescription.Status.PENDING)),
            partial=Count("id", filter=Q(status=Prescription.Status.PARTIAL)),
        )
        pending, partial = counts["pending"] or 0, counts["partial"] or 0
        return Response({"pending": pending, "partial": partial,
                         "total": pending + partial})

    @action(detail=False, url_path="by-number")
    def by_number(self, request):
        """Everything prescribed to whoever this number belongs to.

        ``?number=`` is the patient's phone or their hospital number, written
        however they say it: the match is on the digits (see
        patients.models.number_search_term), so "+234 803 123 4567" and
        "08031234567" find the same person.

        Three lists come back, because a pharmacy is asked to fill three kinds
        of thing and only wants to ask once:

        * ``scripts`` — this tenant's own counter scripts, matched loosely
          (a fragment of the number will do) since its staff may list them all
          anyway;
        * ``orders`` — this tenant's clinician-written drug orders;
        * ``orders_elsewhere`` — drug orders written for that number at
          *another* facility, so a patient prescribed at a hospital can fill it
          at whichever pharmacy they reach. Whole numbers only, and carrying
          the prescription alone (see OutsideOrderSerializer): the number the
          patient hands over is the key to their prescriptions, never to their
          record;
        * ``scripts_elsewhere`` — counter scripts written up under that number
          at *another* pharmacy (one with no stock, say), on the same terms.

        ponytail: a query per list. Fold them together only if a tenant's
        script table ever makes this show up in a plan.
        """
        number = (request.query_params.get("number") or "").strip()
        term = number_search_term(number)
        if len(term) < 4:
            raise ValidationError(
                {"number": "Give at least 4 digits of a phone or hospital number."}
            )
        # The registry is read to match the number, never returned: this
        # endpoint is the pharmacy's, and identifying data is the patient
        # API's (which logs every read of it).
        here = with_survivors(Patient.objects.filter(
            Q(phone__contains=term) | Q(hospital_number__contains=term)
        ))
        scripts = self.get_queryset().filter(
            Q(patient__in=here)
            | Q(customer__phone__contains=term)
            | Q(customer_phone__contains=term)
        )
        orders = DrugOrder.objects.filter(patient__in=here)
        holders = patients_by_number(number)
        tenant_id = getattr(request.tenant, "id", None)
        elsewhere = DrugOrder.all_objects.filter(
            patient__in=holders
        ).exclude(tenant_id=tenant_id).select_related(
            "medication", "reporter", "tenant"
        )
        # A script written up for a walk-in names them by phone alone, so a
        # whole phone number (never a fragment) reaches it too.
        phone = normalize_phone(number)
        by_phone = Q(customer_phone=phone) if len(phone) >= 11 else Q(pk__in=[])
        scripts_elsewhere = Prescription.all_objects.filter(
            Q(patient__in=holders) | by_phone
        ).exclude(tenant_id=tenant_id).select_related("tenant")
        # ``?undispensed=1`` — what the patient standing there can still be
        # handed. The counter asks this far more often than it asks for
        # everything ever written to a number.
        if _is_true(request.query_params.get("undispensed")):
            scripts = scripts.filter(status__in=OPEN)
            orders = orders.filter(status__in=OPEN_ORDERS)
            elsewhere = elsewhere.filter(status__in=OPEN_ORDERS)
            scripts_elsewhere = scripts_elsewhere.filter(status__in=OPEN)
        body = {
            "number": number,
            "scripts": PrescriptionSerializer(scripts, many=True).data,
            "orders": DrugOrderSerializer(orders, many=True).data,
            "orders_elsewhere": OutsideOrderSerializer(elsewhere, many=True).data,
            "scripts_elsewhere": OutsideScriptSerializer(scripts_elsewhere,
                                                         many=True).data,
        }
        # Logged like a patient read and for the same reason: this says a
        # number is registered somewhere and what was written for it, and it
        # answers a pharmacy that has never seen the patient. Fail-closed —
        # if the trail can't be written the answer isn't given.
        PatientAccessLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=PatientAccessLog.Action.LOOKUP, query=number[:255],
            result_count=sum(len(body[k]) for k in
                             ("scripts", "orders", "orders_elsewhere",
                              "scripts_elsewhere")),
        )
        return Response(body)

    @action(detail=True, methods=["post"], url_path="dispense")
    def dispense(self, request, pk=None):
        """Tick lines off as they are handed over.

        Body: ``{"lines": [<id>, ...]}``, or nothing to tick the whole script
        off at once. The status follows what was ticked, so a part-filled
        script comes back PARTIAL without anyone setting it.
        """
        rx = self.get_object()
        if rx.status == Prescription.Status.CANCELLED:
            raise ValidationError({"status": "That script was cancelled."})
        ids = request.data.get("lines")
        lines = PrescriptionItem.all_objects.filter(prescription=rx,
                                                    is_dispensed=False)
        if ids:
            lines = lines.filter(pk__in=ids)
        lines = list(lines)
        if not lines:
            raise ValidationError({"lines": "Nothing on that script is still open."})
        with transaction.atomic():
            for line in lines:
                line.mark_dispensed(user=request.user)
        rx.refresh_from_db()
        return success(f"{len(lines)} line(s) dispensed.",
                       PrescriptionSerializer(rx).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Void a script that will not be filled."""
        rx = self.get_object()
        if rx.status == Prescription.Status.DISPENSED:
            raise ValidationError(
                {"status": "That script has already been dispensed in full."}
            )
        rx.status = Prescription.Status.CANCELLED
        rx.save(update_fields=["status", "updated_at"])
        return success("Prescription cancelled.", PrescriptionSerializer(rx).data)
