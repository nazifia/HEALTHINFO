"""HMO and claims API.

Claims are raised by the sale that generated them and every amount moves
through a transition that says who decided it — there is no endpoint that lets
a client type an amount an insurer owes.
"""
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils.dateparse import parse_date
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
from apps.inventory.views import PharmacyViewSet, body
from config.responses import success

from .models import HMO, Claim, ClaimBatch, HmoEnrollment
from .serializers import (
    AddClaimsSerializer,
    ClaimBatchSerializer,
    ClaimDecisionSerializer,
    ClaimPaymentSerializer,
    ClaimSerializer,
    HMOSerializer,
    HmoEnrollmentSerializer,
)

ZERO = Decimal("0.00")


def _range(request):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD into date objects (None if absent)."""
    return (
        parse_date(request.query_params.get("from", "") or ""),
        parse_date(request.query_params.get("to", "") or ""),
    )


def _apply_range(qs, start, end):
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    return qs


class HMOViewSet(PharmacyViewSet):
    """Insurers the pharmacy bills. Coverage is money policy — admin writes."""

    model = HMO
    serializer_class = HMOSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("is_active",)
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")


class HmoEnrollmentViewSet(PharmacyViewSet):
    """Patients' scheme memberships — the cards staff check at the counter."""

    model = HmoEnrollment
    serializer_class = HmoEnrollmentSerializer
    filterset_fields = ("hmo", "patient", "is_active")
    search_fields = ("member_number", "plan")

    def get_queryset(self):
        return HmoEnrollment.objects.select_related("hmo", "patient")


class ClaimViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """HMO claims from submission to settlement.

    Claims are raised by the sale that generated them, so there is no create
    here; every amount moves through a transition that says who decided it.
    """

    serializer_class = ClaimSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "hmo", "enrollment")
    search_fields = ("reference", "sale__reference")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return Claim.objects.select_related("hmo", "sale", "sale__patient", "batch")

    def _transition(self, request, call, message):
        claim = self.get_object()
        try:
            call(claim)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(message, ClaimSerializer(claim).data)

    def _require_admin(self, request):
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Send the claim to the insurer. Staff may do this."""
        return self._transition(request, lambda c: c.submit(), "Claim submitted.")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Record the insurer's approval, for all or part of the amount."""
        self._require_admin(request)
        data = body(ClaimDecisionSerializer, request)
        return self._transition(
            request, lambda c: c.approve(data.get("amount")), "Claim approved."
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        """Record a refusal and why — a rejected claim can be resubmitted."""
        self._require_admin(request)
        data = body(ClaimDecisionSerializer, request)
        return self._transition(
            request, lambda c: c.reject(data.get("reason", "")), "Claim rejected."
        )

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Bank a remittance against an approved claim."""
        self._require_admin(request)
        data = body(ClaimPaymentSerializer, request)
        return self._transition(
            request, lambda c: c.record_payment(data["amount"]), "Payment recorded."
        )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """What each insurer owes: claimed, approved, paid, still outstanding."""
        start, end = _range(request)
        qs = _apply_range(self.get_queryset(), start, end).exclude(
            status=Claim.Status.CANCELLED
        )
        by_hmo = (qs.values("hmo", "hmo__name")
                  .annotate(claims=Count("id"), claimed=Sum("amount"),
                            approved=Sum("amount_approved"), paid=Sum("amount_paid"))
                  .order_by("-claimed"))
        totals = qs.aggregate(
            claims=Count("id"), claimed=Sum("amount"),
            approved=Sum("amount_approved"), paid=Sum("amount_paid"),
        )
        approved = totals["approved"] or ZERO
        paid = totals["paid"] or ZERO
        return Response({
            "claims": totals["claims"] or 0,
            "claimed": totals["claimed"] or ZERO,
            "approved": approved,
            "paid": paid,
            "outstanding": max(approved - paid, ZERO),
            "by_status": list(qs.values("status").annotate(
                n=Count("id"), amount=Sum("amount")).order_by("status")),
            "by_hmo": [
                {"hmo": row["hmo"], "name": row["hmo__name"],
                 "claims": row["claims"], "claimed": row["claimed"] or ZERO,
                 "approved": row["approved"] or ZERO, "paid": row["paid"] or ZERO,
                 "outstanding": max((row["approved"] or ZERO) - (row["paid"] or ZERO),
                                    ZERO)}
                for row in by_hmo
            ],
        })


class ClaimBatchViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                        mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                        viewsets.GenericViewSet):
    """Monthly claim schedules: one envelope per insurer, one remittance back.

    Creating a batch collects the insurer's unbatched open claims for the
    period, which is the whole job most months; ``add-claims`` is there for the
    ones added by hand afterwards.
    """

    serializer_class = ClaimBatchSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff]
    filterset_fields = ("status", "hmo")
    search_fields = ("reference", "notes")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return ClaimBatch.objects.select_related("hmo")

    def perform_create(self, serializer):
        batch = serializer.save()
        claims = Claim.objects.filter(
            hmo=batch.hmo, batch__isnull=True, status__in=Claim.BATCHABLE,
        )
        if batch.period_start:
            claims = claims.filter(created_at__date__gte=batch.period_start)
        if batch.period_end:
            claims = claims.filter(created_at__date__lte=batch.period_end)
        batch.add_claims(list(claims))

    def _transition(self, call, message):
        batch = self.get_object()
        try:
            call(batch)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        batch.refresh_from_db()
        return success(message, ClaimBatchSerializer(batch).data)

    @action(detail=True, methods=["post"], url_path="add-claims")
    def add_claims(self, request, pk=None):
        """Add named claims (or sweep up the insurer's remaining open ones)."""
        batch = self.get_object()
        data = body(AddClaimsSerializer, request)
        claims = data.get("claims") or list(Claim.objects.filter(
            hmo=batch.hmo, batch__isnull=True, status__in=Claim.BATCHABLE,
        ))
        try:
            moved = batch.add_claims(claims)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(f"{moved} claim(s) added to the batch.",
                       ClaimBatchSerializer(batch).data)

    @action(detail=True, methods=["post"], url_path="submit")
    def submit(self, request, pk=None):
        """Send the schedule and every claim on it."""
        return self._transition(lambda b: b.submit(), "Batch submitted.")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Insurer accepted the whole schedule. Admin only."""
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")
        return self._transition(lambda b: b.approve_all(), "Batch approved.")

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """Allocate one remittance across the batch's claims. Admin only."""
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied("Only the pharmacy admin can settle claims.")
        data = body(ClaimPaymentSerializer, request)
        return self._transition(lambda b: b.record_payment(data["amount"]),
                                "Remittance allocated across the batch.")

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Withdraw the schedule and release its claims."""
        return self._transition(lambda b: b.cancel(), "Batch cancelled.")
