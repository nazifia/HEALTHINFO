from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from config.responses import success

from apps.tenants.models import Jurisdiction, Tenant
from apps.tenants.scope import selected_jurisdiction

from .models import Role, User
from .permissions import (
    INSURER_ROLES, OVERSIGHT_ROLES, PATIENT_ROLES, IsSelfOrModuleAdmin,
    IsTenantMember, is_module_admin,
)
from .serializers import (
    LoginSerializer, OnboardingSerializer, PasswordResetConfirmSerializer,
    PasswordResetSerializer, RegisterSerializer, UserSerializer,
    send_reset_email,
)


class LoginView(TokenObtainPairView):
    """Token endpoint that also accepts a license number (see LoginSerializer)."""

    serializer_class = LoginSerializer


class RegisterViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=["get"])
    def organizations(self, request):
        """Public picker for signup: which organization am I joining?

        Someone without an account has no tenant to detect, so they choose one.
        Only live organizations are listed — a suspended or unapproved tenant
        can't be signed in to anyway.
        """
        rows = Tenant.objects.filter(
            status=Tenant.Status.ACTIVE,
            subscription_status=Tenant.SubscriptionStatus.APPROVED,
        ).values("slug", "name", "kind").order_by("name")
        return Response(list(rows))

    def create(self, request):
        s = RegisterSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        s.save()
        return success("Account created. You can now sign in.", s.data, status=201)


class LogoutViewSet(viewsets.ViewSet):
    """Blacklist a refresh token so it can't mint new access tokens.

    Pair with the client clearing its stored tokens. Access tokens already held
    stay valid until they expire (stateless) — keep ACCESS_TOKEN_LIFETIME short.
    """

    permission_classes = [AllowAny]  # the refresh token itself is the credential

    def create(self, request):
        token = request.data.get("refresh")
        if not token:
            return Response({"detail": "refresh token required"}, status=400)
        try:
            RefreshToken(token).blacklist()
        except TokenError:
            # Already blacklisted / expired / malformed — logout is idempotent.
            pass
        return Response(status=205)


class OnboardingViewSet(viewsets.ViewSet):
    """Public org signup: create a tenant and its first admin in one call."""

    permission_classes = [AllowAny]

    def create(self, request):
        s = OnboardingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return success(
            "Organization created. Sign in to continue.", s.data, status=201
        )

    @action(detail=False, methods=["get"])
    def jurisdictions(self, request):
        """Public list for the signup picker. Flat tree; client groups by level."""
        rows = Jurisdiction.objects.values("id", "name", "level", "parent").order_by(
            "level", "name"
        )
        return Response(list(rows))


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsTenantMember, IsSelfOrModuleAdmin]
    # The seats that are not a facility's staff reach this one to run their own
    # portal's user list — narrowed to that portal's seats in get_queryset, and
    # writable only by the seat flagged is_admin (IsSelfOrModuleAdmin).
    insurer_ok = True
    oversight_ok = True
    # A patient reaches this one to keep their own contact details current.
    # The staff list itself is not theirs to read, so get_queryset narrows them
    # to their own row and this stays the only tenant endpoint they open.
    patient_ok = True
    # Staff link a patient record to its portal account by searching this list,
    # so it answers ?search= on the three things anyone would type. No password
    # or token field is searchable — only what the serializer already returns.
    search_fields = ("username", "phone", "email", "license_number")
    # Platform-wide the list is everyone. These narrow it to one organization's
    # people — a facility, a scheme, a health authority's patch — for the admin
    # whose list is that wide. Each one only ever narrows what get_queryset
    # already allowed, so a scoped seat gains nothing by passing them.
    filterset_fields = ("role", "is_active", "tenant", "hmo")

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            # Inside an organization a super admin reads it and nothing else:
            # the staff list follows the tenant they opened. Only outside one
            # (no tenant on the request) is the platform-wide list theirs.
            tenant = getattr(self.request, "tenant", None)
            if tenant is None:
                # Outside an organization the list is platform-wide, or one
                # state's when they have picked a state to work in. A seat
                # belongs to that state either through the facility it staffs
                # or, for a health authority's own people, through the patch on
                # its row — they staff no facility, and the state's list would
                # otherwise be the one list they never appear in.
                picked = selected_jurisdiction(self.request)
                if picked is None:
                    return User.objects.all()
                tree = picked.subtree()
                return User.objects.filter(
                    Q(tenant__jurisdiction__in=tree) | Q(jurisdiction__in=tree)
                )
            return User.objects.filter(tenant=tenant)
        if user.role in INSURER_ROLES:
            # An insurer runs its own scheme's claims desk: the seats on that
            # scheme and nobody else in the pharmacy — the facility's staff
            # directory is not theirs to read.
            return User.objects.filter(
                tenant_id=user.tenant_id, role=Role.HMO, hmo_id=user.hmo_id
            )
        if user.role in OVERSIGHT_ROLES:
            # A health authority runs the seats inside its own patch. No patch
            # set means no module to run, the same fail-closed rule its
            # rollups use (IsPlatformReader).
            if user.jurisdiction_id is None:
                return User.objects.none()
            return User.objects.filter(
                role=Role.GOVERNMENT, jurisdiction__in=user.jurisdiction.subtree()
            )
        # The patient seat is not staff: their own row and nobody else's, so
        # the list cannot be used to read the facility's staff directory.
        if user.role in PATIENT_ROLES:
            return User.objects.filter(pk=user.pk)
        # Tenant-scoped: only see users of your own tenant.
        return User.objects.filter(tenant=user.tenant)

    def create(self, request, *args, **kwargs):
        # Minting a user into an arbitrary tenant is a platform action. A
        # module admin mints into their own module only — the serializer pins
        # the tenant, scheme or jurisdiction from them (apply_admin_scope) —
        # and self-serve signup (register/onboarding) covers everyone else.
        if not (request.user.is_super_admin or is_module_admin(request.user)):
            raise PermissionDenied("You cannot create users here.")
        return super().create(request, *args, **kwargs)

    def get_permissions(self):
        # Everyone reads their own row, including the seats that belong to no
        # tenant (a government seat) or read only part of one (an insurer) —
        # the client asks for it on every page load to know who is signed in.
        if self.action == "me":
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordResetViewSet(viewsets.ViewSet):
    """Forgotten-password flow: ask for a link, then set a new password.

    Both steps are public, so both are throttled and neither ever confirms
    whether a phone number belongs to an account — the request step answers the
    same way for a known number, an unknown one and one with no email on file.
    """

    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    # Same text however the request turns out.
    _sent = ("If that account exists, a reset link is on its way to the email "
             "address on file.")

    def create(self, request):
        s = PasswordResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.user()
        if user is not None:
            send_reset_email(user)
        return success(self._sent)

    @action(detail=False, methods=["post"])
    def confirm(self, request):
        s = PasswordResetConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return success("Password changed. You can now sign in.")
