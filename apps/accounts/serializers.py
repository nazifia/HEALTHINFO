import re

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.tenants.current import get_current_tenant
from apps.tenants.models import Jurisdiction, Tenant

from .models import (
    LICENSED_ROLES, Role, User, normalize_license, normalize_phone,
)


def visible_users(tenant):
    """Users a request bound to `tenant` is allowed to resolve.

    User is not a TenantOwnedModel — its manager is unscoped — so every lookup
    that turns caller-supplied input into a user has to narrow it by hand or
    one tenant reaches another's staff. NULL-tenant rows (super-admins) stay
    visible everywhere; no tenant bound at all is the platform/CLI path and
    scopes to nothing.
    """
    qs = User.objects.all()
    if tenant is None:
        return qs
    return qs.filter(Q(tenant=tenant) | Q(tenant__isnull=True))


class TenantUserField(serializers.PrimaryKeyRelatedField):
    """A user primary key that only accepts members of the request's tenant.

    Use for any writable FK to User: the auto-generated field would take any
    id in the table, letting a tenant bind another tenant's staff to its rows.
    """

    def get_queryset(self):
        return visible_users(get_current_tenant())


class LoginSerializer(TokenObtainPairSerializer):
    """Sign in with a phone number, or — for licensed clinical cadres — a
    licence number.

    Doctors, nurses, midwives and CHEWs authenticate on ``license_number``
    only: their phone is rejected even when the password is right, so the
    credential that identifies them is always the one their regulator issued.
    Pharmacy staff authenticate on the last 6 digits of their phone only: the
    whole number is rejected the same way, so their credential is always the
    short code. Everyone else keeps signing in with their full phone.
    """

    # Last 6 digits of a phone number: the pharmacy short login.
    _short_phone = re.compile(r"\d{6}")

    # Same text for unknown licence, wrong password and wrong login channel, so
    # the endpoint never confirms which licence numbers exist.
    _failed = "No active account found with the given credentials"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields["license_number"] = serializers.CharField(required=False)

    def validate(self, attrs):
        license_number = normalize_license(attrs.pop("license_number", None))
        phone = (attrs.get(self.username_field) or "").strip()
        # Sign-in resolves only users of the tenant being signed in to, so one
        # organization's credentials never mint a token on another's host.
        tenant = getattr(self.context.get("request"), "tenant", None)
        users = visible_users(tenant)

        if license_number:
            user = users.filter(license_number=license_number).first()
            if user is None:
                raise AuthenticationFailed(self._failed, "no_active_account")
            # Hand the parent the phone it expects; the password is still
            # checked by authenticate() below.
            attrs[self.username_field] = user.phone
        elif self._short_phone.fullmatch(phone):
            # Pharmacy staff sign in with the last 6 digits of their phone. The
            # suffix is not unique by construction, so an ambiguous one is
            # refused rather than guessed; an admin renumbers one of the pair.
            # ponytail: suffix scan; index phone_suffix if pharmacist rows grow.
            matches = list(
                users.filter(role=Role.PHARMACIST, phone__endswith=phone)[:2]
            )
            if len(matches) != 1:
                raise AuthenticationFailed(self._failed, "no_active_account")
            attrs[self.username_field] = matches[0].phone
        elif phone:
            holder = users.filter(phone=phone).first()
            # A licensed user whose licence is on file signs in with it and
            # nothing else. One with no licence yet (a row that predates this
            # field) keeps phone login until an admin fills it in, so nobody is
            # locked out by the rollout.
            if holder is not None and (
                (holder.requires_license and holder.license_number)
                # Pharmacy staff use the short code and nothing else.
                or holder.role == Role.PHARMACIST
            ):
                raise AuthenticationFailed(self._failed, "no_active_account")
        else:
            raise serializers.ValidationError(
                {"phone": "Provide a phone number or a license number."}
            )
        data = super().validate(attrs)
        # authenticate() searches the whole user table; the token is only valid
        # for the tenant the user actually belongs to.
        if tenant is not None and self.user.tenant_id not in (tenant.id, None):
            raise AuthenticationFailed(self._failed, "no_active_account")
        # A client on a shared host can't know which organization a user belongs
        # to until they sign in, so the token answer names it: the client sends
        # it straight back as X-Tenant-ID. Empty for super-admins (no tenant).
        data["tenant"] = self.user.tenant.slug if self.user.tenant_id else ""
        # The slug is what the header needs; the name is what a person reads,
        # so the client can show the organization without a second call.
        data["tenant_name"] = self.user.tenant.name if self.user.tenant_id else ""
        data["role"] = self.user.role
        return data


class UserSerializer(serializers.ModelSerializer):
    # Write-only password: set on create, optional rotation on update. Tenant is
    # writable but the view only honours it for super-admins (see UserViewSet).
    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    # The client arms its inactivity timer from this. The user's own tenant
    # sets it; a user without one (super-admin) falls back to the platform
    # default. 0 means never sign out on idle.
    idle_logout_minutes = serializers.SerializerMethodField()
    license_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    class Meta:
        model = User
        fields = (
            "id", "username", "phone", "email", "role", "tenant", "tenant_name",
            "is_active", "password", "license_number", "idle_logout_minutes",
            "hmo", "jurisdiction",
        )

    def get_idle_logout_minutes(self, obj):
        if obj.tenant_id is None:
            return settings.IDLE_LOGOUT_MINUTES
        return obj.tenant.idle_logout_minutes

    def validate_license_number(self, value):
        return normalize_license(value)

    def validate(self, attrs):
        # A licensed cadre with no licence number could never sign in, so the
        # licence is required whenever the role is one of theirs.
        role = attrs.get("role", getattr(self.instance, "role", None))
        if role in LICENSED_ROLES:
            license_number = attrs.get(
                "license_number", getattr(self.instance, "license_number", None)
            )
            if not license_number:
                raise serializers.ValidationError({
                    "license_number":
                        f"A license number is required for the {role} role.",
                })
        tenant = attrs.get("tenant", getattr(self.instance, "tenant", None))
        # A government seat reads the cross-tenant rollups, and those are
        # refused inside an organization (IsPlatformReader). One bound to a
        # tenant would be signed in to a platform that answers it nothing.
        if role == Role.GOVERNMENT:
            if tenant is not None:
                raise serializers.ValidationError({
                    "tenant": "A government seat belongs to no organization — "
                              "leave it unset.",
                })
            # The rollups it reads narrow to this jurisdiction and everything
            # under it. Without one the seat reads nothing, so refuse the
            # account here rather than mint one that answers empty screens.
            jurisdiction = attrs.get(
                "jurisdiction", getattr(self.instance, "jurisdiction", None)
            )
            if not jurisdiction:
                raise serializers.ValidationError({
                    "jurisdiction": "Choose the jurisdiction this health "
                                    "authority seat answers for.",
                })
        if role == Role.HMO:
            # An insurer signs in to the organization whose claims they answer
            # for, and reads only their own scheme's rows (see insurer_scope).
            # Either half missing is an account that can never read anything.
            hmo = attrs.get("hmo", getattr(self.instance, "hmo", None))
            if not hmo:
                raise serializers.ValidationError({
                    "hmo": "Choose the scheme this insurer seat answers for.",
                })
            if tenant is None:
                raise serializers.ValidationError({
                    "tenant": "Choose the organization whose claims this seat "
                              "answers for.",
                })
            if hmo.tenant_id != tenant.id:
                raise serializers.ValidationError({
                    "hmo": "That scheme belongs to another organization.",
                })
        if role == Role.PHARMACIST:
            # Pharmacy staff sign in with the last 6 digits of their phone and
            # nothing else, so two pharmacists sharing a suffix would lock each
            # other out. Refuse the second one here, where an admin can still
            # pick a different number.
            phone = attrs.get("phone", getattr(self.instance, "phone", "")) or ""
            # Only inside the tenant they sign in to: two pharmacists in
            # different organizations share a suffix without ever colliding.
            tenant = attrs.get("tenant", getattr(self.instance, "tenant", None))
            clashes = visible_users(tenant).filter(
                role=Role.PHARMACIST, phone__endswith=phone[-6:]
            )
            if self.instance is not None:
                clashes = clashes.exclude(pk=self.instance.pk)
            if clashes.exists():
                raise serializers.ValidationError({
                    "phone": "Another pharmacy user's phone number ends in "
                             f"{phone[-6:]}. Their sign-in codes would collide.",
                })
        return attrs

    def validate_username(self, value):
        # Store blank as NULL (field is null=True) so empty display names are
        # consistently absent, not "" — the client renders absent as "—".
        return value.strip() or None

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        # role is NOT registrable: a public endpoint that let the caller pick
        # their own role is privilege escalation to super_admin. Forced below.
        fields = ("id", "username", "phone", "email", "password")

    def validate_username(self, value):
        return value.strip() or None

    def validate(self, attrs):
        # A user with no tenant belongs to no organization: they'd fail every
        # tenant-scoped permission and still be visible from every tenant.
        # The client picks one from /api/auth/register/organizations/.
        if getattr(self.context["request"], "tenant", None) is None:
            raise serializers.ValidationError(
                {"tenant": "Choose the organization you are joining."}
            )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        # New users are bound to the request tenant; role is always public.
        request = self.context["request"]
        user = User(tenant=request.tenant, role=Role.PUBLIC, **validated_data)
        user.set_password(password)
        user.save()
        return user


class OnboardingSerializer(serializers.Serializer):
    """Self-serve org signup: create a Tenant + its first tenant_admin user.

    Public endpoint (no tenant context). Tenant and admin are created together
    in one transaction so a failed user never leaves an orphan tenant.
    """

    org_name = serializers.CharField(max_length=200)
    org_slug = serializers.SlugField(max_length=50)
    org_kind = serializers.ChoiceField(
        choices=Tenant.Kind.choices, default=Tenant.Kind.PHARMACY
    )
    org_address = serializers.CharField(required=False, allow_blank=True)
    org_contact = serializers.CharField(max_length=120, required=False, allow_blank=True)
    # The tenant's own jurisdiction (usually its local gov). Optional so signup
    # still works offline of the tree; rollup just skips tenants with none.
    jurisdiction = serializers.PrimaryKeyRelatedField(
        queryset=Jurisdiction.objects.all(), required=False, allow_null=True
    )
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_org_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This slug is already taken.")
        return value

    def validate_phone(self, value):
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("This phone number is already taken.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        tenant = Tenant.objects.create(
            name=validated_data["org_name"],
            slug=validated_data["org_slug"],
            kind=validated_data["org_kind"],
            address=validated_data.get("org_address", ""),
            contact=validated_data.get("org_contact", ""),
            jurisdiction=validated_data.get("jurisdiction"),
            subscription_status=Tenant.SubscriptionStatus.PENDING,
        )
        user = User(
            phone=validated_data["phone"],
            email=validated_data.get("email", ""),
            tenant=tenant,
            role=Role.TENANT_ADMIN,
        )
        user.set_password(validated_data["password"])
        user.save()
        self.instance = {"tenant": tenant, "user": user}
        return self.instance

    def to_representation(self, instance):
        tenant, user = instance["tenant"], instance["user"]
        return {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "address": tenant.address,
                "contact": tenant.contact,
                "jurisdiction": tenant.jurisdiction_id,
                "jurisdiction_name": (
                    str(tenant.jurisdiction) if tenant.jurisdiction_id else None
                ),
            },
            "user": {"id": user.id, "phone": user.phone, "role": user.role},
        }


class PasswordResetSerializer(serializers.Serializer):
    """Ask for a reset link, identified the way a patient signs in: by phone.

    Deliberately unscoped by tenant. Someone who has forgotten their password
    has also usually forgotten which organization slug their app is pointed at,
    and phone is unique across the table anyway. Nothing here tells the caller
    whether the number is known — see the view.
    """

    phone = serializers.CharField()

    def validate_phone(self, value):
        return normalize_phone(value)

    def user(self):
        """The account to mail, or None. Never raises: not-found is not an
        error the caller is allowed to see."""
        return User.objects.filter(
            phone=self.validated_data["phone"], is_active=True
        ).first()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Set a new password from the uid + token pair that was mailed out.

    The token is Django's own ``default_token_generator``: an HMAC over the
    user's id, current password hash and last login, so it needs no storage,
    expires on its own (PASSWORD_RESET_TIMEOUT) and stops working the moment
    the password changes — which makes it single-use for free.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])

    _bad = "This reset link has expired or has already been used."

    def validate(self, attrs):
        try:
            pk = urlsafe_base64_decode(attrs["uid"]).decode()
            user = User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": self._bad})
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": self._bad})
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        return user


def send_reset_email(user):
    """Mail a reset link. Best-effort, like every other mail in this codebase.

    ponytail: email only, because email is the one channel this deployment
    already has. Patients sign in by phone, so set FRONTEND_URL and — when an
    SMS gateway exists — send the same two values down it from right here.
    """
    if not user.email:
        return False
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/#/reset?uid={uid}&token={token}"
    send_mail(
        "Reset your password",
        f"Open this link to choose a new password:\n\n{link}\n\n"
        f"It stops working in {settings.PASSWORD_RESET_TIMEOUT // 60} minutes. "
        "If you did not ask for this, ignore this message.",
        None,  # DEFAULT_FROM_EMAIL
        [user.email],
        fail_silently=True,
    )
    return True
