"""Minting a user refuses bad input with a 400, never a 500 or a dead row."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="T", slug="t", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )


@pytest.fixture
def admin(tenant):
    c = APIClient()
    c.force_authenticate(User.objects.create_user(
        phone="08030000001", role=Role.TENANT_ADMIN, tenant=tenant, password="x"
    ))
    return c


def mint(admin, tenant, **body):
    return admin.post("/api/users/", {"password": "pass12345!", **body},
                      format="json", HTTP_X_TENANT_ID=tenant.slug)


def test_same_phone_in_another_shape_is_a_400_not_a_crash(admin, tenant):
    User.objects.create_user(phone="08031234567", tenant=tenant, password="x")
    r = mint(admin, tenant, phone="+234 803 123 4567")
    assert r.status_code == 400 and "phone" in r.json()["errors"]


def test_phone_typed_with_spaces_is_folded_and_accepted(admin, tenant):
    r = mint(admin, tenant, phone="0803 123 4567")
    assert r.status_code == 201, r.content
    assert r.json()["phone"] == "08031234567"


def test_duplicate_licence_is_a_400_not_a_crash(admin, tenant):
    User.objects.create_user(phone="08031234567", tenant=tenant, password="x",
                             role=Role.DOCTOR, license_number="MDCN-1")
    r = mint(admin, tenant, phone="08031234568", role="doctor",
             license_number="mdcn/1", accept_terms=True)
    assert r.status_code == 400 and "license_number" in r.json()["errors"]


def test_onboarding_refuses_a_non_phone(db):
    r = APIClient().post("/api/auth/onboarding/", {
        "org_name": "X", "org_slug": "x", "phone": "not-a-phone",
        "password": "Sup3r-Str0ng-Pw!",
    }, format="json")
    assert r.status_code == 400 and "phone" in r.json()["errors"]
    assert not User.objects.exists()


def test_onboarding_refuses_a_taken_phone_in_another_shape(db, tenant):
    User.objects.create_user(phone="08031234567", tenant=tenant, password="x")
    r = APIClient().post("/api/auth/onboarding/", {
        "org_name": "X", "org_slug": "x", "phone": "+2348031234567",
        "password": "Sup3r-Str0ng-Pw!",
    }, format="json")
    assert r.status_code == 400 and "phone" in r.json()["errors"]


def test_register_refuses_a_taken_phone_in_another_shape(db, tenant):
    User.objects.create_user(phone="08031234567", tenant=tenant, password="x")
    r = APIClient().post("/api/auth/register/", {
        "phone": "+2348031234567", "password": "Sup3r-Str0ng-Pw!",
    }, format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 400 and "phone" in r.json()["errors"]
