"""Catalog list endpoints actually return the tenant's rows.

Regression guard: viewsets used to set `queryset = Model.objects.all()` at
class-body level, which froze the tenant-scoped manager to an empty `.none()`
at import time (no tenant bound yet). Lists came back empty for everyone.
TenantQuerysetMixin re-runs the manager per request; these tests fail if that
regresses, and also pin the public-role published-only filter (MRO ordering).
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def env(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    pub = Disease.objects.create(name="Malaria", slug="malaria", status="published")
    Disease.objects.create(name="Cholera", slug="cholera", status="draft")
    yield t, pub
    clear_current_tenant()


def _get(client, slug):
    return client.get("/api/diseases/", HTTP_X_TENANT_ID=slug)


def test_list_returns_tenant_rows(env):
    t, _ = env
    doctor = User.objects.create(phone="+2348039990001", tenant=t, role=Role.DOCTOR)
    client = APIClient()
    client.force_authenticate(doctor)

    r = _get(client, t.slug)
    assert r.status_code == 200
    # Staff sees every status: both the published and the draft row.
    assert r.data["count"] == 2


def test_public_sees_only_published(env):
    t, _ = env
    public = User.objects.create(phone="+2348039990002", tenant=t, role=Role.PUBLIC)
    client = APIClient()
    client.force_authenticate(public)

    r = _get(client, t.slug)
    assert r.status_code == 200
    names = {row["name"] for row in r.data["results"]}
    assert names == {"Malaria"}  # draft "Cholera" hidden
