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
    PUBLIC = "public"


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

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN or self.is_superuser
