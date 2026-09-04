import re

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models

from apps.tenants.models import Tenant


class Role(models.TextChoices):
    SUPER_ADMIN = "super_admin"
    TENANT_ADMIN = "tenant_admin"
    DOCTOR = "doctor"
    PHARMACIST = "pharmacist"
    NURSE = "nurse"
    MIDWIFE = "midwife"
    CHEW = "chew", "Community Health Extension Worker"
    PUBLIC = "public"


# Clinical cadres that hold a practising licence. They sign in with that licence
# number instead of a phone number — the licence is the credential their
# regulator issues and the one they can be verified against.
LICENSED_ROLES = frozenset({Role.DOCTOR, Role.NURSE, Role.MIDWIFE, Role.CHEW})


# Nigerian mobile: local 0XXXXXXXXXX (11 digits) or international +234XXXXXXXXXX,
# network code starting 7/8/9 (e.g. 08031234567 or +2348031234567).
# ponytail: regex only; swap for phonenumbers lib if you need carrier-level checks.
phone_validator = RegexValidator(
    regex=r"^(?:\+234|0)[789]\d{9}$",
    message="Enter a valid Nigerian phone number (e.g. 08031234567 or +2348031234567).",
)


def normalize_phone(value):
    """One shape for a Nigerian number: local ``0XXXXXXXXXX``.

    Drops spaces, dashes and brackets and folds ``+234``/``234`` onto the
    leading 0, so "+234 803 123 4567" and "0803-123-4567" stop being two
    different patients. Anything that isn't a Nigerian mobile comes back
    stripped but otherwise untouched, for the validator to reject.
    """
    digits = re.sub(r"[^\d+]", "", value or "")
    for prefix in ("+234", "234"):
        if digits.startswith(prefix):
            return "0" + digits[len(prefix):]
    return digits


# Licence numbers come from several registers (MDCN, NMCN, CHPRBN) with no one
# shared format, so we only normalize shape: strip separators, fold to upper.
# ponytail: no per-register format check; add one when a register's rule is fixed.
def normalize_license(value):
    return re.sub(r"[\s/\-]+", "", (value or "").strip()).upper() or None


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        if not phone:
            raise ValueError("The phone number must be set")
        email = self.normalize_email(extra_fields.pop("email", "") or "")
        user = self.model(phone=phone, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(phone, password, **extra_fields)


class User(AbstractUser):
    # Phone is the login identifier. Username is kept as an optional display
    # name only (no longer unique, no longer used to authenticate).
    username = models.CharField(max_length=150, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, validators=[phone_validator])

    # Login identifier for LICENSED_ROLES; NULL for everyone else. Unique, but
    # NULLs don't collide in SQL so unlicensed users all sit at NULL happily.
    license_number = models.CharField(
        max_length=50, null=True, blank=True, unique=True
    )

    # Super-admins have no tenant (platform-wide). Everyone else is scoped.
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="users"
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.PUBLIC
    )

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        # One shape for the licence whatever wrote the row — the API
        # serializer, the Django admin, a management command. Sign-in looks the
        # number up already normalized (see normalize_license), so a row saved
        # with its separators still on it could never be signed in to.
        self.license_number = normalize_license(self.license_number)
        super().save(*args, **kwargs)

    @property
    def requires_license(self):
        """True when this user signs in with a licence number, not a phone."""
        return self.role in LICENSED_ROLES

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN or self.is_superuser
