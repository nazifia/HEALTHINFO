"""Short-phone login for pharmacy staff.

Pharmacists sign in with the last 6 digits of their phone number; the full
number stops working. An ambiguous suffix is refused rather than guessed.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PASSWORD = "s3curepass99"


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    yield t
    clear_current_tenant()


def make_user(tenant, phone, role):
    user = User.objects.create(phone=phone, tenant=tenant, role=role)
    user.set_password(PASSWORD)
    user.save()
    return user


def token(**body):
    return APIClient().post(
        "/api/auth/token/", body, format="json", HTTP_X_TENANT_ID="clinic"
    )


def test_pharmacist_signs_in_with_last_six_digits(tenant):
    make_user(tenant, "+2348031234567", Role.PHARMACIST)
    ok = token(phone="234567", password=PASSWORD)
    assert ok.status_code == 200, ok.content
    assert ok.json()["access"]


def test_pharmacist_cannot_use_full_phone(tenant):
    make_user(tenant, "+2348031234567", Role.PHARMACIST)
    assert token(phone="+2348031234567", password=PASSWORD).status_code == 401


def test_short_login_is_pharmacy_only(tenant):
    make_user(tenant, "+2348037654321", Role.TENANT_ADMIN)
    assert token(phone="654321", password=PASSWORD).status_code == 401


def test_ambiguous_suffix_is_refused(tenant):
    make_user(tenant, "08031111111", Role.PHARMACIST)
    make_user(tenant, "08091111111", Role.PHARMACIST)
    assert token(phone="111111", password=PASSWORD).status_code == 401


def test_wrong_password_and_unknown_suffix_are_401(tenant):
    make_user(tenant, "+2348031234567", Role.PHARMACIST)
    assert token(phone="234567", password="wrong-one").status_code == 401
    assert token(phone="999999", password=PASSWORD).status_code == 401


def test_admin_cannot_create_two_pharmacists_with_the_same_suffix(tenant):
    admin = make_user(tenant, "+2348035555555", Role.SUPER_ADMIN)
    admin.is_superuser = True
    admin.save()
    make_user(tenant, "08031111111", Role.PHARMACIST)
    client = APIClient()
    client.force_authenticate(admin)

    body = {"phone": "08091111111", "role": Role.PHARMACIST, "tenant": tenant.id}
    clash = client.post("/api/users/", body, format="json", HTTP_X_TENANT_ID="clinic")
    assert clash.status_code == 400, clash.content
    assert "phone" in clash.json()["errors"]

    ok = client.post(
        "/api/users/", {**body, "phone": "08092222222"}, format="json",
        HTTP_X_TENANT_ID="clinic",
    )
    assert ok.status_code == 201, ok.content
