from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from config.responses import success

from .models import Role, User
from .permissions import IsTenantMember
from .serializers import OnboardingSerializer, RegisterSerializer, UserSerializer


class RegisterViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

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


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return User.objects.all()
        # Tenant-scoped: only see users of your own tenant.
        return User.objects.filter(tenant=user.tenant)

    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response(UserSerializer(request.user).data)
