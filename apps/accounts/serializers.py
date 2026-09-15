import re

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.tenants.current import get_current_tenant
from apps.tenants.models import Jurisdiction, Tenant

from .models import (
    LICENSED_ROLES, Role, User, normalize_license, normalize_phone,
    phone_validator,
)
from .permissions import (
    ALL_PRIVILEGES, granted, is_module_admin, manageable_roles,
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


def apply_admin_scope(actor, attrs, instance=None):
    """Pin a write to /api/users/ inside the writer's own module.

    A super admin writes anything. A module admin — the facility's tenant
    admin, a flagged insurer seat, a flagged health authority seat — mints and
    edits seats of their own module only, so the fields that decide *which*
    module a user belongs to are taken from the admin, never from the body: an
    insurer admin cannot mint a pharmacist, and an authority admin cannot mint
    a seat reading the next state's rollups.

    Everyone else may still edit their own contact details, but the fields that
    carry privilege are dropped rather than refused — a member patching their
    own row shouldn't 400 because the client echoed their role back.
    """
    if actor.is_super_admin:
        return
    if not is_module_admin(actor):
        # license_number too: the licence is the identity a prescriber's
        # cross-tenant statement (MyDuesView) is keyed on, so changing it is
        # changing whose dues you read — an admin's decision, not yours. And
        # is_active: a seat stays open until an admin closes it, so a profile
        # form echoing the flag back unticked cannot lock its owner out.
        for field in ("tenant", "role", "is_admin", "hmo", "jurisdiction",
                      "privileges", "license_number", "is_active"):
            attrs.pop(field, None)
        return
    if "privileges" in attrs:
        # You grant what you hold and nothing more: a pharmacist trusted with
        # the user list cannot hand themselves the money screens too.
        wanted = set(attrs["privileges"] or [])
        beyond = wanted - granted(actor)
        if beyond:
            raise serializers.ValidationError({
                "privileges": "You cannot grant: " + ", ".join(sorted(beyond)),
            })
        attrs["privileges"] = sorted(wanted)
    role = attrs.get("role") or getattr(instance, "role", None) or (
        Role.PUBLIC if actor.role == Role.TENANT_ADMIN else actor.role
    )
    if role not in manageable_roles(actor):
        raise serializers.ValidationError(
            {"role": f"You cannot assign the {role} role."}
        )
    attrs["role"] = role
    if actor.role == Role.GOVERNMENT:
        # An authority seat belongs to no organization, and reads the patch its
        # admin answers for or a smaller one inside it — never a sibling's.
        attrs["tenant"] = None
        patch = attrs.get("jurisdiction") or actor.jurisdiction
        if not actor.jurisdiction.subtree().filter(pk=patch.pk).exists():
            raise serializers.ValidationError(
                {"jurisdiction": "That jurisdiction is outside your patch."}
            )
        attrs["jurisdiction"] = patch
        return
    attrs["jurisdiction"] = None
    attrs["tenant"] = actor.tenant
    if actor.role == Role.HMO:
        attrs["hmo"] = actor.hmo
    elif role != Role.HMO:
        attrs["hmo"] = None


class FoldedField(serializers.CharField):
    """A text field folded to one shape *before* its validators run.

    User.save stores the phone and the licence normalized, so a uniqueness
    check on what was typed ("+234 803...", "mdcn/1") misses the row already
    holding "0803..." / "MDCN1" and the insert dies on the DB constraint
    instead of answering a 400. Folding first makes the validators see the
    same shape the table does.
    """

    def __init__(self, fold, **kwargs):
        self.fold = fold
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return self.fold(super().to_internal_value(data))


def phone_field(**kwargs):
    return FoldedField(normalize_phone, validators=[
        phone_validator,
        UniqueValidator(User.objects.all(),
                        message="This phone number is already taken."),
    ], **kwargs)


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
            # Rows are stored folded (User.save), so "+234 803..." typed at
            # the login screen folds the same way to find its row — unless a
            # row minted before folding kept its old spelling because another
            # row already held the folded one. The spelling typed wins and the
            # folded one is the fallback, so neither of such a pair is locked
            # out of the number it has always signed in with.
            holder = (users.filter(phone=phone).first()
                      or users.filter(phone=normalize_phone(phone)).first())
            if holder is not None:
                phone = holder.phone
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
            attrs[self.username_field] = phone
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
    """One user row, as an admin's form or the user's own profile writes it.

    Creation: ``password`` is required, the writer's module pins tenant/scheme/
    jurisdiction (apply_admin_scope), and the role decides what else the row
    must carry (``_ROLE_CHECKS``). The row itself is minted through
    ``User.objects.create_user`` so the API, the shell and the seed script all
    open a seat the same way.
    """

    # Write-only. Required when minting (validate says so — declaring it
    # required here would mark it required on the edit form's OPTIONS too);
    # blank on edit keeps the current one.
    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    # The client arms its inactivity timer from this. The user's own tenant
    # sets it; a user without one (super-admin) falls back to the platform
    # default. 0 means never sign out on idle.
    idle_logout_minutes = serializers.SerializerMethodField()
    phone = phone_field()
    license_number = FoldedField(
        normalize_license, required=False, allow_blank=True, allow_null=True,
        validators=[UniqueValidator(
            User.objects.all(),
            message="Another user already holds this license number.",
        )],
    )
    # Named grants, checked against the catalog so a typo is a 400 rather than
    # a row carrying a privilege no gate will ever read.
    privileges = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(ALL_PRIVILEGES)),
        required=False,
    )
    # A prescriber's agreement to the Healthcare Terms and Conditions
    # (accounts.terms, served at /api/auth/register/terms/). Required to open
    # a licensed seat; stamped on the row as ``terms_accepted_at``.
    accept_terms = serializers.BooleanField(
        write_only=True, required=False, default=False,
        label="The prescriber has read and agrees to the Healthcare Terms "
              "and Conditions",
    )

    class Meta:
        model = User
        fields = (
            "id", "username", "phone", "email", "role", "tenant", "tenant_name",
            "is_active", "password", "license_number", "idle_logout_minutes",
            "hmo", "jurisdiction", "is_admin", "privileges", "is_independent",
            "accept_terms", "terms_accepted_at",
        )
        read_only_fields = ("is_independent", "terms_accepted_at")

    def get_idle_logout_minutes(self, obj):
        if obj.tenant_id is None:
            return settings.IDLE_LOGOUT_MINUTES
        return obj.tenant.idle_logout_minutes

    def validate_username(self, value):
        # Store blank as NULL (field is null=True) so empty display names are
        # consistently absent, not "" — the client renders absent as "—".
        return value.strip() or None

    def validate_license_number(self, value):
        # Blank skips FoldedField (DRF returns "" before to_internal_value), so
        # fold it here too: the column is NULL for everyone unlicensed.
        return normalize_license(value)

    # ----- cross-field validation -------------------------------------------

    def validate(self, attrs):
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            apply_admin_scope(request.user, attrs, self.instance)
        errors = {}
        # A seat minted without a password cannot sign in, and nothing on the
        # form said so: refuse it here instead of opening a dead one.
        if self.instance is None and not attrs.get("password"):
            errors["password"] = "Set a password so this user can sign in."
        seat = self._seat(attrs)
        for check in self._ROLE_CHECKS.get(seat["role"], ()):
            errors.update(check(self, seat, attrs))
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _seat(self, attrs):
        """The row as it will stand after this write: the body over the instance."""
        names = ("role", "tenant", "hmo", "jurisdiction", "license_number",
                 "phone", "terms_accepted_at")
        seat = {n: attrs[n] if n in attrs else getattr(self.instance, n, None)
                for n in names}
        seat["role"] = seat["role"] or Role.PUBLIC   # the model default
        return seat

    def _check_licence(self, seat, attrs):
        # A licensed cadre signs in with the licence, so a seat without one
        # could never sign in; and no seat for a prescriber who has not agreed
        # to the terms. Asked once: a row already stamped is not asked again.
        errors = {}
        if not seat["license_number"]:
            errors["license_number"] = (
                f"A license number is required for the {seat['role']} role."
            )
        if not seat["terms_accepted_at"] and not attrs.get("accept_terms"):
            errors["accept_terms"] = (
                "The prescriber must agree to the Healthcare Terms and "
                "Conditions before the account is opened."
            )
        return errors

    def _check_independent(self, seat, attrs):
        # A licensed clinician with no employer writes under the facilities of
        # the state on their licence. Without one they could pick no facility
        # at all (may_prescribe_under fails closed), so refuse the seat here.
        if seat["tenant"] is not None:
            return {}
        state = seat["jurisdiction"]
        if not state:
            return {"jurisdiction": "An independent prescriber writes under the "
                                    "facilities of one state — choose it, or "
                                    "choose the organization they work for."}
        if state.level != Jurisdiction.Level.STATE:
            return {"jurisdiction": "Choose a state: a licence is registered "
                                    "state-wide, not per local government."}
        return {}

    def _check_authority(self, seat, attrs):
        # A government seat reads the cross-tenant rollups, which are refused
        # inside an organization (IsPlatformReader), and narrowed to its
        # jurisdiction and everything under it. Bound to a tenant, or with no
        # patch, it would sign in to a platform that answers it nothing. The
        # national tier is the whole country — the platform admin's view — so
        # it is refused here and fails closed on the read side (User.has_patch).
        errors = {}
        if seat["tenant"] is not None:
            errors["tenant"] = ("A government seat belongs to no organization — "
                                "leave it unset.")
        patch = seat["jurisdiction"]
        if not patch:
            errors["jurisdiction"] = ("Choose the jurisdiction this health "
                                      "authority seat answers for.")
        elif patch.level == Jurisdiction.Level.NATIONAL:
            errors["jurisdiction"] = ("A health authority answers for a state "
                                      "or a local government, not the country.")
        return errors

    def _check_insurer(self, seat, attrs):
        # An insurer signs in to the organization whose claims they answer for
        # and reads only their own scheme's rows (see insurer_scope). Either
        # half missing is an account that can never read anything.
        hmo, tenant = seat["hmo"], seat["tenant"]
        if not hmo:
            return {"hmo": "Choose the scheme this insurer seat answers for."}
        if tenant is None:
            return {"tenant": "Choose the organization whose claims this seat "
                              "answers for."}
        if hmo.tenant_id != tenant.id:
            return {"hmo": "That scheme belongs to another organization."}
        return {}

    def _check_pharmacist_suffix(self, seat, attrs):
        # Pharmacy staff sign in with the last 6 digits of their phone and
        # nothing else, so two pharmacists sharing a suffix would lock each
        # other out. Refuse the second one here, where an admin can still pick
        # a different number. Only inside the tenant they sign in to: two
        # pharmacists in different organizations never collide.
        suffix = (seat["phone"] or "")[-6:]
        clashes = visible_users(seat["tenant"]).filter(
            role=Role.PHARMACIST, phone__endswith=suffix
        )
        if self.instance is not None:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            return {"phone": "Another pharmacy user's phone number ends in "
                             f"{suffix}. Their sign-in codes would collide."}
        return {}

    _ROLE_CHECKS = dict.fromkeys(LICENSED_ROLES, (_check_licence, _check_independent))
    _ROLE_CHECKS.update({
        Role.GOVERNMENT: (_check_authority,),
        Role.HMO: (_check_insurer,),
        Role.PHARMACIST: (_check_pharmacist_suffix,),
    })

    # ----- persistence ------------------------------------------------------

    def _stamp_terms(self, validated_data):
        # The flag is not a column; agreeing becomes a timestamp, once.
        agreed = validated_data.pop("accept_terms", False)
        if agreed and not getattr(self.instance, "terms_accepted_at", None):
            validated_data["terms_accepted_at"] = timezone.now()

    def create(self, validated_data):
        self._stamp_terms(validated_data)
        return User.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        self._stamp_terms(validated_data)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class RegisterSerializer(serializers.ModelSerializer):
    """Self-serve patient signup into one organization."""

    phone = phone_field()
    password = serializers.CharField(write_only=True, validators=[validate_password])

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
        # Bound to the request tenant; role is always public.
        return User.objects.create_user(
            tenant=self.context["request"].tenant, role=Role.PUBLIC,
            **validated_data,
        )


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
    phone = phone_field()
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_org_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("This slug is already taken.")
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
        user = User.objects.create_user(
            phone=validated_data["phone"],
            password=validated_data["password"],
            email=validated_data.get("email", ""),
            tenant=tenant,
            role=Role.TENANT_ADMIN,
        )
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
