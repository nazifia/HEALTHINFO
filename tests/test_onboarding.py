"""Org self-signup: creates a tenant + its first admin, atomically."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


@pytest.fixture
def client():
    return APIClient()


def test_onboarding_creates_tenant_and_admin(db, client):
    resp = client.post(
        "/api/auth/onboarding/",
        {
            "org_name": "Hospital A",
            "org_slug": "hospital-a",
            "phone": "+2348031230001",
            "email": "admin@a.com",
            "password": "Sup3r-Str0ng-Pw!",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    # Success envelope: message + the data keys the client reads, side by side.
    assert resp.data["success"] is True
    assert resp.data["message"]
    assert resp.data["tenant"]["slug"] == "hospital-a"
    tenant = Tenant.objects.get(slug="hospital-a")
    user = User.objects.get(phone="+2348031230001")
    assert user.tenant_id == tenant.id
    assert user.role == Role.TENANT_ADMIN
    assert user.check_password("Sup3r-Str0ng-Pw!")


def test_failure_uses_message_envelope(db, client):
    resp = client.post(
        "/api/auth/onboarding/",
        {"org_slug": "BAD SLUG"},  # missing fields + invalid slug
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["success"] is False
    assert isinstance(resp.data["message"], str) and resp.data["message"]
    assert resp.data["errors"]  # field errors preserved for the form to use


def test_onboarding_sets_jurisdiction(db, client):
    from apps.tenants.models import Jurisdiction

    lga = Jurisdiction.objects.create(name="Ikeja", level="local")
    resp = client.post(
        "/api/auth/onboarding/",
        {
            "org_name": "Geo Org",
            "org_slug": "geo-org",
            "jurisdiction": lga.id,
            "phone": "+2348031230009",
            "email": "geo@org.com",
            "password": "Sup3r-Str0ng-Pw!",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.data["tenant"]["jurisdiction"] == lga.id
    assert Tenant.objects.get(slug="geo-org").jurisdiction_id == lga.id


def test_onboarding_rejects_duplicate_slug(db, client):
    Tenant.objects.create(name="Existing", slug="taken")
    resp = client.post(
        "/api/auth/onboarding/",
        {
            "org_name": "New Org",
            "org_slug": "taken",
            "phone": "+2348031230002",
            "email": "new@org.com",
            "password": "Sup3r-Str0ng-Pw!",
        },
        format="json",
    )
    assert resp.status_code == 400
    # No orphan tenant/user left behind.
    assert User.objects.filter(phone="+2348031230002").count() == 0


def test_onboarding_weak_password_no_orphan_tenant(db, client):
    resp = client.post(
        "/api/auth/onboarding/",
        {
            "org_name": "Weak Org",
            "org_slug": "weak-org",
            "phone": "+2348031230003",
            "email": "weak@org.com",
            "password": "123",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert Tenant.objects.filter(slug="weak-org").count() == 0
