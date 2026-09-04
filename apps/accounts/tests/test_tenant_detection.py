"""Sign-in tells the client which organization the user belongs to.

A client on a shared host sends no X-Tenant-ID at login; the token answer
names the user's tenant so every later call is scoped to the right one.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PASSWORD = "s3curepass99"


@pytest.fixture
def tenants(db):
    a = Tenant.objects.create(name="Clinic A", slug="clinic-a")
    b = Tenant.objects.create(name="Clinic B", slug="clinic-b")
    yield a, b
    clear_current_tenant()


def make_user(tenant, phone, role=Role.TENANT_ADMIN):
    user = User.objects.create(phone=phone, tenant=tenant, role=role)
    user.set_password(PASSWORD)
    user.save()
    return user


def token(**headers):
    return APIClient().post(
        "/api/auth/token/",
        {"phone": "08031234567", "password": PASSWORD},
        format="json",
        **headers,
    )


def test_login_without_a_tenant_header_reports_the_users_own_tenant(tenants):
    _, b = tenants
    make_user(b, "08031234567")
    r = token()
    assert r.status_code == 200, r.content
    assert r.json()["tenant"] == "clinic-b"
    assert r.json()["role"] == Role.TENANT_ADMIN


def test_super_admin_reports_no_tenant(tenants):
    user = User.objects.create(phone="08031234567", role=Role.SUPER_ADMIN)
    user.set_password(PASSWORD)
    user.save()
    r = token()
    assert r.status_code == 200, r.content
    assert r.json()["tenant"] == ""


def test_a_bound_tenant_still_refuses_another_tenants_user(tenants):
    a, b = tenants
    make_user(b, "08031234567")
    r = token(HTTP_X_TENANT_ID=a.slug)
    assert r.status_code == 401, r.content


def test_signup_picker_lists_only_live_organizations(tenants):
    a, b = tenants
    b.subscription_status = Tenant.SubscriptionStatus.PENDING
    b.save(update_fields=["subscription_status"])
    r = APIClient().get("/api/auth/register/organizations/")
    assert r.status_code == 200, r.content
    assert [o["slug"] for o in r.json()] == [a.slug]


def test_register_without_an_organization_is_refused(tenants):
    r = APIClient().post(
        "/api/auth/register/",
        {"phone": "08039998877", "email": "x@example.com", "password": PASSWORD},
        format="json",
    )
    assert r.status_code == 400, r.content
    assert not User.objects.filter(phone="08039998877").exists()


def test_register_joins_the_chosen_organization(tenants):
    a, _ = tenants
    r = APIClient().post(
        "/api/auth/register/",
        {"phone": "08039998877", "email": "x@example.com", "password": PASSWORD},
        format="json",
        HTTP_X_TENANT_ID=a.slug,
    )
    assert r.status_code == 201, r.content
    assert User.objects.get(phone="08039998877").tenant_id == a.id
