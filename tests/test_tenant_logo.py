"""The receipt logo: a tenant admin sets their own, the platform admin sets
any tenant's from its record, and both paths refuse the same things."""
import base64

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Clinic", slug="clinic")


def _client(user, slug=None):
    c = APIClient()
    c.force_authenticate(user)
    if slug:
        c.credentials(HTTP_X_TENANT_ID=slug)
    return c


def test_tenant_admin_sets_own_logo(tenant):
    admin = User.objects.create_user(
        phone="08030000020", password="x", role=Role.TENANT_ADMIN, tenant=tenant,
    )
    c = _client(admin, tenant.slug)
    assert c.patch("/api/tenants/settings/", {"logo": PNG}, format="json").status_code == 200
    tenant.refresh_from_db()
    assert tenant.logo == PNG
    assert c.patch("/api/tenants/settings/", {"logo": "data:text/html;base64,PGI+"},
                   format="json").status_code == 400
    assert c.patch("/api/tenants/settings/", {"logo": ""}, format="json").status_code == 200
    tenant.refresh_from_db()
    assert tenant.logo == ""


def test_super_admin_sets_any_tenants_logo(tenant):
    boss = User.objects.create_user(
        phone="08030000021", password="x", role=Role.SUPER_ADMIN,
        is_staff=True, is_superuser=True,
    )
    c = _client(boss)
    assert c.patch(f"/api/tenants/{tenant.id}/", {"logo": PNG}, format="json").status_code == 200
    tenant.refresh_from_db()
    assert tenant.logo == PNG
    bad = c.patch(f"/api/tenants/{tenant.id}/", {"logo": "not a data url"}, format="json")
    assert bad.status_code == 400
    assert "logo" in bad.json().get("errors", bad.json())
    tenant.refresh_from_db()
    assert tenant.logo == PNG
