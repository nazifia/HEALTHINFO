"""A super-admin inside one organization sees that organization only.

Opening a clinic or a pharmacy means working as it: the cross-tenant platform
rollups are refused while the request carries a tenant, and the staff list
follows the tenant instead of the whole platform. Leaving it (no X-Tenant-ID)
restores the platform view.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenants(db):
    a = Tenant.objects.create(name="Clinic A", slug="clinic-a")
    b = Tenant.objects.create(name="Pharmacy B", slug="pharmacy-b")
    yield a, b
    clear_current_tenant()


def _super(db):
    return User.objects.create_user(
        phone="08050000001", password="x", role=Role.SUPER_ADMIN,
        is_staff=True, is_superuser=True,
    )


def _case(tenant, disease_name):
    set_current_tenant(tenant)
    disease = Disease.objects.create(name=disease_name, slug=disease_name.lower())
    report = CaseReport.objects.create(disease=disease)
    clear_current_tenant()
    return report


def test_platform_rollup_refused_inside_a_tenant(tenants, client):
    a, _ = tenants
    client.force_authenticate(_super(None))
    assert client.get("/api/analytics/platform/sources/").status_code == 200
    resp = client.get("/api/analytics/platform/sources/", HTTP_X_TENANT_ID=a.slug)
    assert resp.status_code == 403


def test_tenant_rollup_counts_only_the_opened_tenant(tenants, client):
    a, b = tenants
    _case(a, "Malaria")
    _case(b, "Cholera")
    _case(b, "Typhoid")
    client.force_authenticate(_super(None))

    resp = client.get("/api/analytics/sources/", HTTP_X_TENANT_ID=a.slug)
    assert resp.status_code == 200
    assert resp.data["total_cases"] == 1
    # ...and the other organization's rows are the ones missing, not a filter
    # that happens to count one row.
    resp = client.get("/api/analytics/sources/", HTTP_X_TENANT_ID=b.slug)
    assert resp.data["total_cases"] == 2


def test_user_list_follows_the_opened_tenant(tenants, client):
    a, b = tenants
    User.objects.create_user(phone="08050000002", password="x", tenant=a)
    User.objects.create_user(phone="08050000003", password="x", tenant=b)
    client.force_authenticate(_super(None))

    rows = client.get("/api/users/", HTTP_X_TENANT_ID=a.slug).data["results"]
    assert [r["phone"] for r in rows] == ["08050000002"]

    # Outside every organization the platform-wide list is theirs again.
    rows = client.get("/api/users/").data["results"]
    assert len(rows) == 3


def test_tenant_switcher_stays_reachable_inside_a_tenant(tenants, client):
    a, _ = tenants
    client.force_authenticate(_super(None))
    # The way back out must not be locked behind the platform scope.
    assert client.get("/api/tenants/", HTTP_X_TENANT_ID=a.slug).status_code == 200
