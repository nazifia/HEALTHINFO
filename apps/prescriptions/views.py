"""Prescriptions API: scripts filled at the counter, and what they earn the
prescriber.

Money owed to a prescriber is raised by the sale that generated it, never
posted by a client — so there is no create on commissions or payouts, only the
transition that settles one.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsPharmacyAdminOrReadOnly,
    IsPharmacyStaff,
    IsTenantMember,
    is_pharmacy_admin,
)
from apps.inventory.views import PharmacyViewSet
from config.responses import success

from .models import (
    ConsultationPayout,
    Hospital,
    Prescriber,
    PrescriberCommission,
    Prescription,
    PrescriptionItem,
)
from .serializers import (
    ConsultationPayoutSerializer,
    HospitalSerializer,
    PrescriberCommissionSerializer,
    PrescriberSerializer,
    PrescriptionSerializer,
)

ZERO = Decimal("0.00")


class HospitalViewSet(PharmacyViewSet):
    """Clinics and hospitals prescribers write from."""

    model = Hospital
    serializer_class = HospitalSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    search_fields = ("name", "city", "phone")
    ordering_fields = ("name", "created_at")


class PrescriberViewSet(PharmacyViewSet):
    """Doctors whose scripts this pharmacy fills.

    Commission rates and consultation bands are money policy, so writing them
    is the admin's; every dispenser reads the list.
    """

    model = Prescriber
    serializer_class = PrescriberSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("hospital", "is_verified", "is_active")
    search_fields = ("name", "license_number", "specialty", "clinic")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        return Prescriber.objects.select_related("hospital")

    @action(detail=True, methods=["get"], url_path="statement")
    def statement(self, request, pk=None):
        """What this prescriber has earned and what is still owed."""
        prescriber = self.get_object()
        commissions = PrescriberCommission.objects.filter(prescriber=prescriber)
        payouts = ConsultationPayout.objects.filter(prescriber=prescriber)
        return Response({
            "prescriber": prescriber.pk,
            "name": prescriber.name,
            "outstanding": prescriber.outstanding,
            "commissions": PrescriberCommissionSerializer(
                commissions, many=True
            ).data,
            "consultation_payouts": ConsultationPayoutSerializer(
                payouts, many=True
            ).data,
        })


class PrescriptionViewSet(PharmacyViewSet):
    """Scripts presented at the counter and what has been filled off them."""

    model = Prescription
    serializer_class = PrescriptionSerializer
    filterset_fields = ("status", "source", "prescriber", "customer", "patient",
                        "branch")
    search_fields = ("customer_name", "customer_phone", "doctor_name", "diagnosis")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return Prescription.objects.select_related(
            "prescriber", "customer", "branch"
        ).prefetch_related("lines")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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


class _PrescriberDueViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    """Money owed to a prescriber. Raised by a sale; settled here.

    Read is open to pharmacy staff; paying is the admin's, because it is the
    pharmacy's money going out.
    """

    permission_classes = [IsTenantMember, IsPharmacyStaff]
    amount_field = None
    model = None

    def get_queryset(self):
        return self.model.objects.select_related("prescriber", "prescription")

    def _require_admin(self):
        if not is_pharmacy_admin(self.request.user):
            raise PermissionDenied("Only the pharmacy admin can settle a prescriber.")

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Settle one entry."""
        self._require_admin()
        due = self.get_object()
        try:
            due.mark_paid()
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success("Marked paid.", self.get_serializer(due).data)

    @action(detail=False, methods=["post"], url_path="pay-all")
    def pay_all(self, request, pk=None):
        """Settle everything still pending, optionally for one prescriber.

        Body: ``{"prescriber": <id>}`` to pay one; omit it to clear the lot.
        """
        self._require_admin()
        qs = self.get_queryset().filter(status=self.model.Status.PENDING)
        prescriber = request.data.get("prescriber")
        if prescriber:
            qs = qs.filter(prescriber_id=prescriber)
        rows = list(qs)
        total = ZERO
        with transaction.atomic():
            for row in rows:
                total += getattr(row, self.amount_field)
                row.mark_paid()
        return success(f"{len(rows)} entr(ies) settled, {total} in total.",
                       {"settled": len(rows), "amount": total})

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """What is owed and what has been paid, by prescriber."""
        rows = (self.get_queryset()
                .values("prescriber", "prescriber__name", "status")
                .annotate(n=Count("id"), amount=Sum(self.amount_field))
                .order_by("prescriber__name"))
        return Response(list(rows))


class PrescriberCommissionViewSet(_PrescriberDueViewSet):
    """A share of each sale made on a prescriber's script."""

    model = PrescriberCommission
    serializer_class = PrescriberCommissionSerializer
    amount_field = "commission_amount"
    filterset_fields = ("prescriber", "prescription", "status")
    ordering_fields = ("created_at", "commission_amount")


class ConsultationPayoutViewSet(_PrescriberDueViewSet):
    """The flat consultation fee charged at the till and owed to the writer."""

    model = ConsultationPayout
    serializer_class = ConsultationPayoutSerializer
    amount_field = "consultation_fee"
    filterset_fields = ("prescriber", "status")
    ordering_fields = ("created_at", "consultation_fee")
