"""Auto sign-out timeout: who may change it, and what the client is told.

The number lives on the tenant. A tenant admin sets their own organization's;
a super-admin sets any tenant's through the tenant CRUD. Everyone else reads
it on /users/me/ and nothing more.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Clinic", slug="clinic")


def _client(user, slug=None):
    c = APIClient()
    c.force_authenticate(user)
    if slug:
        c.credentials(HTTP_X_TENANT_ID=slug)
    return c


def test_default_and_me_exposes_tenant_value(tenant):
    assert tenant.idle_logout_minutes == 30
    tenant.idle_logout_minutes = 5
    tenant.save()
    user = User.objects.create_user(
        phone="08030000010", password="x", role=Role.PHARMACIST, tenant=tenant,
    )
    resp = _client(user, tenant.slug).get("/api/users/me/")
    assert resp.status_code == 200
    assert resp.json()["idle_logout_minutes"] == 5


def test_super_admin_without_tenant_gets_platform_default(db, settings):
    settings.IDLE_LOGOUT_MINUTES = 15
    boss = User.objects.create_user(
        phone="08030000011", password="x", role=Role.SUPER_ADMIN,
        is_staff=True, is_superuser=True,
    )
    resp = _client(boss).get("/api/users/me/")
    assert resp.json()["idle_logout_minutes"] == 15


def test_tenant_admin_sets_own_timeout(tenant):
    admin = User.objects.create_user(
        phone="08030000012", password="x", role=Role.TENANT_ADMIN, tenant=tenant,
    )
    c = _client(admin, tenant.slug)
    assert c.get("/api/tenants/settings/").json()["idle_logout_minutes"] == 30

    resp = c.patch("/api/tenants/settings/", {"idle_logout_minutes": 10}, format="json")
    assert resp.status_code == 200
    tenant.refresh_from_db()
    assert tenant.idle_logout_minutes == 10

    # Out of range and non-numeric are refused, not silently clamped.
    assert c.patch("/api/tenants/settings/", {"idle_logout_minutes": 5000},
                   format="json").status_code == 400
    assert c.patch("/api/tenants/settings/", {"idle_logout_minutes": "soon"},
                   format="json").status_code == 400


def test_non_admin_member_cannot_change_it(tenant):
    doc = User.objects.create_user(
        phone="08030000013", password="x", role=Role.DOCTOR, tenant=tenant,
    )
    c = _client(doc, tenant.slug)
    assert c.patch("/api/tenants/settings/", {"idle_logout_minutes": 0},
                   format="json").status_code == 403
    tenant.refresh_from_db()
    assert tenant.idle_logout_minutes == 30


def test_tenant_admin_cannot_touch_the_rest_of_the_tenant(tenant):
    """The settings endpoint only ever writes the timeout."""
    admin = User.objects.create_user(
        phone="08030000014", password="x", role=Role.TENANT_ADMIN, tenant=tenant,
    )
    c = _client(admin, tenant.slug)
    c.patch("/api/tenants/settings/",
            {"idle_logout_minutes": 7, "status": "suspended",
             "subscription_plan": "enterprise"}, format="json")
    tenant.refresh_from_db()
    assert tenant.idle_logout_minutes == 7
    assert tenant.status == Tenant.Status.ACTIVE
    assert tenant.subscription_plan == "free"
    # And the tenant list stays shut to them.
    assert c.get("/api/tenants/").status_code == 403


def test_super_admin_sets_any_tenants_timeout(tenant):
    boss = User.objects.create_user(
        phone="08030000015", password="x", role=Role.SUPER_ADMIN,
        is_staff=True, is_superuser=True,
    )
    resp = _client(boss).patch(f"/api/tenants/{tenant.id}/",
                               {"idle_logout_minutes": 45}, format="json")
    assert resp.status_code == 200
    tenant.refresh_from_db()
    assert tenant.idle_logout_minutes == 45
