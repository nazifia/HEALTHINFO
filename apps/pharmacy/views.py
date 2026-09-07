"""HMO and claims API.

Claims are raised by the sale that generated them and every amount moves
through a transition that says who decided it — there is no endpoint that lets
a client type an amount an insurer owes.
"""
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q, Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    INSURER_ROLES,
    IsPharmacyAdminOrReadOnly,
    IsPharmacyStaff,
    IsPharmacyStaffOrInsurerReadOnly,
    IsTenantMember,
    is_pharmacy_admin,
)
from apps.governance.models import AuditLog
from apps.governance.serializers import AuditLogSerializer
from apps.inventory.views import PharmacyViewSet, body
from config.ranges import apply_range as _apply_range, date_range as _range
from config.responses import success

from .models import (
    HMO,
    Claim,
    ClaimBatch,
    HmoEnrollment,
    HmoItemRule,
    PreAuthorization,
    PreAuthorizationItem,
)
from .serializers import (
    AddClaimsSerializer,
    ClaimBatchSerializer,
    ClaimDecisionSerializer,
    ClaimPaymentSerializer,
    ClaimSerializer,
    HMOSerializer,
    HmoEnrollmentSerializer,
    HmoItemRuleSerializer,
    PreAuthDecisionSerializer,
    PreAuthItemDecisionSerializer,
    PreAuthorizationItemSerializer,
    PreAuthorizationSerializer,
)

ZERO = Decimal("0.00")


def insurer_scope(qs, user, field="hmo"):
    """Narrow to the scheme an insurer seat answers for; everyone else sees all.

    An insurer signs in to the pharmacy's tenant, so tenant scoping alone would
    hand them a competitor's claims. A seat with no scheme set reads nothing.
    """
    if user.is_authenticated and user.role in INSURER_ROLES:
        return qs.filter(**{field: user.hmo_id})
    return qs


class HMOViewSet(PharmacyViewSet):
    """Insurers the pharmacy bills. Coverage is money policy — admin writes."""

    model = HMO
    serializer_class = HMOSerializer
    permission_classes = [
        IsTenantMember, IsPharmacyStaffOrInsurerReadOnly, IsPharmacyAdminOrReadOnly,
    ]
    insurer_ok = True
    filterset_fields = ("is_active",)
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")

    def get_queryset(self):
        return insurer_scope(HMO.objects.all(), self.request.user, field="pk")


class HmoItemRuleViewSet(PharmacyViewSet):
    """Per-drug cover: what one scheme pays for one item, 0 being an exclusion.

    Money policy, so admin writes and the counter only reads.
    """

    model = HmoItemRule
    serializer_class = HmoItemRuleSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaff, IsPharmacyAdminOrReadOnly]
    filterset_fields = ("hmo", "item")
    search_fields = ("item__name", "note")
    ordering_fields = ("coverage_percent", "created_at")

    def get_queryset(self):
        return HmoItemRule.objects.select_related("hmo", "item")


class PreAuthorizationViewSet(PharmacyViewSet):
    """Clearances asked of an insurer before a high-value covered sale.

    Staff raise the request; only the admin records what the insurer answered,
    because that answer is what the pharmacy is later allowed to bill against.
    """

    model = PreAuthorization
    serializer_class = PreAuthorizationSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaffOrInsurerReadOnly]
    insurer_ok = True
    filterset_fields = ("status", "hmo", "enrollment")
    search_fields = ("reference", "code", "notes")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return insurer_scope(PreAuthorization.objects.select_related(
            "hmo", "enrollment", "enrollment__patient", "sale"
        ), self.request.user)

    def perform_create(self, serializer):
        """The insurer's answer goes back to whoever asked."""
        serializer.save(requested_by=self.request.user)

    def _transition(self, call, message):
        auth = self.get_object()
        try:
            call(auth)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(message, PreAuthorizationSerializer(auth).data)

    def _require_admin(self, request):
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied(
                "Only the pharmacy admin can record an insurer's decision."
            )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Record the clearance: their code, the amount, and when it lapses."""
        self._require_admin(request)
        data = body(PreAuthDecisionSerializer, request)
        return self._transition(
            lambda a: a.approve(code=data.get("code", ""),
                                amount=data.get("amount"),
                                expires_on=data.get("expires_on")),
            "Authorisation recorded.",
        )

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        """Record a refusal and why."""
        self._require_admin(request)
        data = body(PreAuthDecisionSerializer, request)
        return self._transition(lambda a: a.decline(data.get("reason", "")),
                                "Authorisation declined.")

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        """Undo a wrong answer so the right one can be recorded."""
        self._require_admin(request)
        data = body(PreAuthDecisionSerializer, request)
        return self._transition(
            lambda a: a.reopen(data.get("reason", ""), by=request.user),
            "Answer withdrawn - record it again.")

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """Who withdrew an answer on this request, and when. Newest first.

        The request and its medications share one trail: an answer undone on a
        medication is what put the request itself back to unanswered, so a
        dispute over what the insurer was told reads both in one place.
        """
        auth = self.get_object()
        logs = AuditLog.objects.filter(
            Q(content_type=ContentType.objects.get_for_model(PreAuthorization),
              object_id=auth.pk)
            | Q(content_type=ContentType.objects.get_for_model(
                    PreAuthorizationItem),
                object_id__in=auth.items.values_list("pk", flat=True))
        )
        return Response(AuditLogSerializer(logs, many=True).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Withdraw the request - the sale was not made after all."""
        data = body(PreAuthDecisionSerializer, request)
        return self._transition(lambda a: a.cancel(data.get("reason", "")),
                                "Request withdrawn.")


class PreAuthorizationItemViewSet(mixins.ListModelMixin,
                                  mixins.RetrieveModelMixin,
                                  viewsets.GenericViewSet):
    """The insurer's answer to one ordered medication on a request.

    Lines are raised with the request itself, so there is no create here. Only
    the admin records a decision — the same rule the request as a whole follows,
    because a cleared drug is money the pharmacy may bill for.
    """

    serializer_class = PreAuthorizationItemSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaffOrInsurerReadOnly]
    insurer_ok = True
    filterset_fields = ("authorization", "status", "item")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return insurer_scope(
            PreAuthorizationItem.objects.select_related("item", "authorization"),
            self.request.user, field="authorization__hmo",
        )

    def _decide(self, request, call, message):
        if not is_pharmacy_admin(request.user):
            raise PermissionDenied(
                "Only the pharmacy admin can record an insurer's decision."
            )
        line = self.get_object()
        try:
            call(line)
        except ValueError as exc:
            raise ValidationError({"status": str(exc)}) from exc
        return success(message, PreAuthorizationItemSerializer(line).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        """Clear this medication, for all or part of what was asked for it."""
        data = body(PreAuthItemDecisionSerializer, request)
        return self._decide(
            request,
            lambda l: l.approve(data.get("amount"), data.get("quantity")),
            "Medication authorised.")

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        """Refuse this medication and say why — it is not dispensed on cover."""
        data = body(PreAuthItemDecisionSerializer, request)
        return self._decide(request, lambda l: l.decline(data.get("reason", "")),
                            "Medication declined.")

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        """Undo a wrong answer to this medication so it can be recorded again."""
        data = body(PreAuthItemDecisionSerializer, request)
        return self._decide(
            request,
            lambda l: l.reopen(data.get("reason", ""), by=request.user),
            "Answer withdrawn - record it again.")


class HmoEnrollmentViewSet(PharmacyViewSet):
    """Patients' scheme memberships — the cards staff check at the counter."""

    model = HmoEnrollment
    serializer_class = HmoEnrollmentSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaffOrInsurerReadOnly]
    insurer_ok = True
    filterset_fields = ("hmo", "patient", "is_active")
    search_fields = ("member_number", "plan")

    def get_queryset(self):
        return insurer_scope(
            HmoEnrollment.objects.select_related("hmo", "patient"), self.request.user
        )


class ClaimViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """HMO claims from submission to settlement.

    Claims are raised by the sale that generated them, so there is no create
    here; every amount moves through a transition that says who decided it.
    """

    serializer_class = ClaimSerializer
    permission_classes = [IsTenantMember, IsPharmacyStaffOrInsurerReadOnly]
    insurer_ok = True
    filterset_fields = ("status", "hmo", "enrollment")
    search_fields = ("reference", "sale__reference")
    ordering_fields = ("created_at", "amount")

    def get_queryset(self):
        return insurer_scope(
            Claim.objects.select_related("hmo", "sale", "sale__patient", "batch"),
            self.request.user,
        )

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

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Stop billing for a claim. Admin only — it writes off insured money."""
        self._require_admin(request)
        data = body(ClaimDecisionSerializer, request)
        return self._transition(
            request, lambda c: c.cancel(data.get("reason", "")), "Claim cancelled."
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
    permission_classes = [IsTenantMember, IsPharmacyStaffOrInsurerReadOnly]
    insurer_ok = True
    filterset_fields = ("status", "hmo")
    search_fields = ("reference", "notes")
    ordering_fields = ("created_at",)

    def get_queryset(self):
        return insurer_scope(ClaimBatch.objects.select_related("hmo"),
                             self.request.user)

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
