"""A member of one tenant cannot read another's screens by sending its slug.

The manager scopes every query to the tenant on the request, and that tenant
comes from a header the client picks. What makes that safe is IsTenantMember
refusing a user whose own tenant is not the one on the request — so every
tenant-scoped route has to carry it. This sweeps them all rather than
trusting each new view to remember.
"""
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant
from config.urls import _api_endpoints

# Answers the same for everyone, or answers only for the caller's own row.
TENANT_FREE = {
    "/api/",
    "/api/health/",
    "/api/schema/",
    "/api/docs/",
    "/api/auth/register/organizations/",
    "/api/auth/logout/",
    "/api/auth/onboarding/",
    "/api/auth/password-reset/",
    # The caller's own row, whatever tenant the header names.
    "/api/users/me/",
    # Facilities an independent prescriber may pick; empty for everyone else.
    "/api/tenants/prescribing/",
    # A public directory of live pharmacies: cross-tenant on purpose.
    "/api/portal/pharmacies/",
}


@pytest.fixture
def two_tenants(db):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    admin = User.objects.create(phone="08030000001", tenant=a, role=Role.TENANT_ADMIN)
    return a, b, admin


def test_every_get_route_refuses_another_tenants_slug(two_tenants):
    a, b, admin = two_tenants
    client = APIClient()
    client.force_authenticate(admin)
    leaked = []
    for route in _api_endpoints():
        if route in TENANT_FREE or route.startswith("/api/auth/"):
            continue
        for method in (client.get, client.post):
            resp = method(route, {}, format="json", HTTP_X_TENANT_ID=b.slug)
            # 400 means the body was validated: the permission never ran.
            if resp.status_code not in (401, 403, 404, 405):
                leaked.append((route, method.__name__, resp.status_code))
    assert leaked == [], leaked


def test_settings_patch_refuses_another_tenants_slug(two_tenants):
    a, b, admin = two_tenants
    client = APIClient()
    client.force_authenticate(admin)
    resp = client.patch("/api/tenants/settings/", {"idle_logout_minutes": 5},
                        format="json", HTTP_X_TENANT_ID=b.slug)
    assert resp.status_code == 403, resp.content
    b.refresh_from_db()
    assert b.idle_logout_minutes == 30


def test_shift_refuses_another_tenants_user(two_tenants):
    a, b, admin = two_tenants
    outsider = User.objects.create(phone="08030000002", tenant=b, role=Role.PHARMACIST)
    client = APIClient()
    client.force_authenticate(admin)
    body = {"user": outsider.id, "starts_at": "2026-09-14T08:00:00Z",
            "ends_at": "2026-09-14T16:00:00Z"}
    resp = client.post("/api/shifts/", body, format="json", HTTP_X_TENANT_ID=a.slug)
    assert resp.status_code == 400, resp.content
    assert "user" in resp.json()["errors"]


def test_self_edit_cannot_change_license_number(two_tenants):
    a, b, _ = two_tenants
    doctor = User.objects.create(phone="08030000003", tenant=a, role=Role.DOCTOR,
                                 license_number="MDCN1",
                                 terms_accepted_at=timezone.now())
    client = APIClient()
    client.force_authenticate(doctor)
    resp = client.patch(f"/api/users/{doctor.id}/", {"license_number": "MDCN2"},
                        format="json", HTTP_X_TENANT_ID=a.slug)
    assert resp.status_code == 200, resp.content
    doctor.refresh_from_db()
    assert doctor.license_number == "MDCN1"
