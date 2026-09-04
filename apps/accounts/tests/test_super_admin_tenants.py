"""A super-admin works inside any organization, not just approved ones.

They belong to no tenant, so they reach one by sending its slug as
X-Tenant-ID. The subscription gate must not shut them out of a pending
tenant — reviewing it is exactly their job.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PASSWORD = "s3curepass99"


@pytest.fixture
def pending_tenant(db):
    tenant = Tenant.objects.create(
        name="Clinic P",
        slug="clinic-p",
        subscription_status=Tenant.SubscriptionStatus.PENDING,
    )
    yield tenant
    clear_current_tenant()


def super_admin_client(tenant_slug):
    user = User.objects.create(phone="08031234567", role=Role.SUPER_ADMIN)
    user.set_password(PASSWORD)
    user.save()
    client = APIClient()
    r = client.post(
        "/api/auth/token/",
        {"phone": user.phone, "password": PASSWORD},
        format="json",
    )
    assert r.status_code == 200, r.content
    # No home tenant of their own; they pick the one they want to work in.
    assert r.json()["tenant"] == ""
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}",
        HTTP_X_TENANT_ID=tenant_slug,
    )
    return client


def test_super_admin_works_inside_a_pending_tenant(pending_tenant):
    client = super_admin_client(pending_tenant.slug)
    r = client.get("/api/users/")
    assert r.status_code == 200, r.content


def test_a_tenants_own_admin_is_still_gated(pending_tenant):
    user = User.objects.create(
        phone="08039998877", tenant=pending_tenant, role=Role.TENANT_ADMIN
    )
    user.set_password(PASSWORD)
    user.save()
    client = APIClient()
    r = client.post(
        "/api/auth/token/",
        {"phone": user.phone, "password": PASSWORD},
        format="json",
        HTTP_X_TENANT_ID=pending_tenant.slug,
    )
    assert r.status_code == 200, r.content
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}",
        HTTP_X_TENANT_ID=pending_tenant.slug,
    )
    assert client.get("/api/users/").status_code == 403


def test_an_anonymous_caller_is_still_gated(pending_tenant):
    r = APIClient().get("/api/users/", HTTP_X_TENANT_ID=pending_tenant.slug)
    assert r.status_code == 403


def test_opening_a_tenant_is_recorded_and_readable(pending_tenant):
    client = super_admin_client(pending_tenant.slug)
    r = client.post(f"/api/tenants/{pending_tenant.id}/open/")
    assert r.status_code == 200, r.content

    r = client.get(f"/api/tenants/{pending_tenant.id}/access-log/")
    assert r.status_code == 200, r.content
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["to_status"] == "opened"
    assert rows[0]["user_phone"] == "08031234567"


def test_the_trail_is_readable_with_no_tenant_bound(pending_tenant):
    """The reader carries no tenant header of their own — the scoped manager
    would answer with nothing, so the endpoint must bypass it."""
    client = super_admin_client(pending_tenant.slug)
    assert client.post(f"/api/tenants/{pending_tenant.id}/open/").status_code == 200
    client.credentials(**{
        k: v for k, v in client._credentials.items() if k != "HTTP_X_TENANT_ID"
    })
    r = client.get(f"/api/tenants/{pending_tenant.id}/access-log/")
    assert r.status_code == 200, r.content
    assert len(r.json()) == 1


def test_a_tenant_admin_cannot_open_or_read_the_trail(pending_tenant):
    user = User.objects.create(
        phone="08039998877", tenant=pending_tenant, role=Role.TENANT_ADMIN
    )
    user.set_password(PASSWORD)
    user.save()
    client = APIClient()
    r = client.post(
        "/api/auth/token/",
        {"phone": user.phone, "password": PASSWORD},
        format="json",
        HTTP_X_TENANT_ID=pending_tenant.slug,
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert client.post(f"/api/tenants/{pending_tenant.id}/open/").status_code == 403
    assert client.get(f"/api/tenants/{pending_tenant.id}/access-log/").status_code == 403
