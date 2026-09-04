"""Licence-number login for the clinical cadres.

Doctors, nurses, midwives and CHEWs sign in with the licence number their
regulator issued; their phone number stops working once that licence is on
file. Everyone else still signs in with a phone.
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


def make_user(tenant, phone, role, license_number=None):
    user = User.objects.create(
        phone=phone, tenant=tenant, role=role, license_number=license_number
    )
    user.set_password(PASSWORD)
    user.save()
    return user


def token(**body):
    return APIClient().post(
        "/api/auth/token/", body, format="json", HTTP_X_TENANT_ID="clinic"
    )


@pytest.mark.parametrize(
    "role", [Role.DOCTOR, Role.NURSE, Role.MIDWIFE, Role.CHEW]
)
def test_licensed_roles_sign_in_with_license(tenant, role):
    number = f"LIC{role.upper()}1"
    make_user(tenant, f"+23480310000{Role.values.index(role):02d}", role, number)

    ok = token(license_number=number, password=PASSWORD)
    assert ok.status_code == 200, ok.content
    assert ok.json()["access"]

    # Separators and case are normalized, so "lic-doctor 1" is the same licence.
    loose = token(license_number=f"  lic-{role} 1 ", password=PASSWORD)
    assert loose.status_code == 200, loose.content


def test_licensed_role_cannot_use_phone(tenant):
    make_user(tenant, "+2348031111111", Role.DOCTOR, "MDCN12345")
    resp = token(phone="+2348031111111", password=PASSWORD)
    assert resp.status_code == 401, resp.content


def test_licensed_role_without_license_keeps_phone_login(tenant):
    # Rows predating the licence field must not be locked out.
    make_user(tenant, "+2348032222222", Role.NURSE)
    resp = token(phone="+2348032222222", password=PASSWORD)
    assert resp.status_code == 200, resp.content


def test_unlicensed_roles_still_use_phone(tenant):
    # Pharmacy staff are the other exception; see test_pharmacy_login.py.
    make_user(tenant, "+2348033333333", Role.TENANT_ADMIN)
    assert token(phone="+2348033333333", password=PASSWORD).status_code == 200


def test_unknown_license_and_wrong_password_are_401(tenant):
    make_user(tenant, "+2348034444444", Role.MIDWIFE, "NMCN999")
    assert token(license_number="NOPE", password=PASSWORD).status_code == 401
    assert token(license_number="NMCN999", password="wrong-one").status_code == 401


def test_missing_identifier_is_400(tenant):
    assert token(password=PASSWORD).status_code == 400


def test_admin_cannot_create_licensed_user_without_license(tenant):
    admin = make_user(tenant, "+2348035555555", Role.SUPER_ADMIN)
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(admin)

    body = {"phone": "+2348036666666", "role": Role.CHEW, "tenant": tenant.id}
    bad = client.post("/api/users/", body, format="json", HTTP_X_TENANT_ID="clinic")
    assert bad.status_code == 400, bad.content
    assert "license_number" in bad.json()["errors"]

    good = client.post(
        "/api/users/", {**body, "license_number": "chprbn/77"}, format="json",
        HTTP_X_TENANT_ID="clinic",
    )
    assert good.status_code == 201, good.content
    assert User.objects.get(phone="+2348036666666").license_number == "CHPRBN77"


def test_a_license_written_straight_to_the_row_still_signs_in(db):
    """The seed and the Django admin write the licence as the regulator prints
    it. Sign-in looks it up normalized, so the row has to be stored that way
    however it was written."""
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    try:
        make_user(t, "+2348031000090", Role.DOCTOR, "demo-doctor-002")
        assert User.objects.get(phone="+2348031000090").license_number == \
            "DEMODOCTOR002"
        r = token(license_number="DEMO-DOCTOR-002", password=PASSWORD)
        assert r.status_code == 200, r.content
    finally:
        clear_current_tenant()
