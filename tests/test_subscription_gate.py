"""Pending/rejected tenants are blocked at the middleware before any view."""
import pytest
from rest_framework.test import APIClient

from apps.tenants.models import Tenant


@pytest.fixture
def client():
    return APIClient()


def _get(client, slug):
    return client.get("/api/catalog/diseases/", HTTP_X_TENANT_ID=slug)


def test_pending_tenant_blocked(db, client):
    Tenant.objects.create(
        name="Pend", slug="pend",
        subscription_status=Tenant.SubscriptionStatus.PENDING,
    )
    resp = _get(client, "pend")
    assert resp.status_code == 403
    assert resp.json()["success"] is False


def test_rejected_tenant_blocked(db, client):
    Tenant.objects.create(
        name="Rej", slug="rej",
        subscription_status=Tenant.SubscriptionStatus.REJECTED,
    )
    assert _get(client, "rej").status_code == 403


def test_pending_tenant_can_reach_login(db, client):
    Tenant.objects.create(
        name="Pend", slug="pend",
        subscription_status=Tenant.SubscriptionStatus.PENDING,
    )
    # Login route whitelisted: not blocked by the gate (bad creds -> 401, not 403).
    resp = client.post(
        "/api/auth/token/", {"phone": "x", "password": "y"},
        format="json", HTTP_X_TENANT_ID="pend",
    )
    assert resp.status_code != 403


def test_approved_tenant_allowed(db, client):
    Tenant.objects.create(
        name="Ok", slug="ok",
        subscription_status=Tenant.SubscriptionStatus.APPROVED,
    )
    # Not 403 — middleware lets it through (auth/view may still 401/200).
    assert _get(client, "ok").status_code != 403
