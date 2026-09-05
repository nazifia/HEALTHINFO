"""The one test that must never break: tenants cannot see each other's data."""
import pytest

from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenants(db):
    a = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    b = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    yield a, b
    clear_current_tenant()


def test_manager_scopes_to_current_tenant(tenants):
    a, b = tenants
    set_current_tenant(a)
    Disease.objects.create(name="Malaria", slug="malaria")
    set_current_tenant(b)
    Disease.objects.create(name="Cholera", slug="cholera")

    set_current_tenant(a)
    names = set(Disease.objects.values_list("name", flat=True))
    assert names == {"Malaria"}

    set_current_tenant(b)
    names = set(Disease.objects.values_list("name", flat=True))
    assert names == {"Cholera"}


def test_no_tenant_bound_returns_nothing(tenants):
    a, _ = tenants
    set_current_tenant(a)
    Disease.objects.create(name="Malaria", slug="malaria")

    clear_current_tenant()
    # Missing tenant context must never leak rows.
    assert Disease.objects.count() == 0
    # Escape hatch still sees everything.
    assert Disease.all_objects.count() == 1


def test_save_auto_assigns_current_tenant(tenants):
    a, _ = tenants
    set_current_tenant(a)
    d = Disease.objects.create(name="Typhoid", slug="typhoid")
    assert d.tenant_id == a.id


def test_global_rows_visible_to_every_tenant(tenants):
    a, b = tenants
    # Global reference row: created with no tenant bound (tenant stays NULL).
    clear_current_tenant()
    Disease.all_objects.create(name="Measles", slug="measles", tenant=None)

    set_current_tenant(a)
    Disease.objects.create(name="Malaria", slug="malaria")  # A-private

    # A sees its own + global; never B's private rows.
    set_current_tenant(a)
    assert set(Disease.objects.values_list("name", flat=True)) == {"Malaria", "Measles"}
    # B sees only global (no private rows of its own yet).
    set_current_tenant(b)
    assert set(Disease.objects.values_list("name", flat=True)) == {"Measles"}


# --- Sign-in and staff references are scoped too -----------------------------
# The manager only scopes rows that carry a tenant. User does not, so the two
# places that turn caller input into a user — the token endpoint and any
# writable FK to User — are checked here.

PASSWORD = "s3curepass99"


def _staff(tenant, phone, role):
    from apps.accounts.models import User

    u = User.objects.create(phone=phone, tenant=tenant, role=role)
    u.set_password(PASSWORD)
    u.save()
    return u


def test_login_refused_on_another_tenants_host(tenants):
    from rest_framework.test import APIClient

    from apps.accounts.models import Role

    a, b = tenants
    _staff(a, "08031234567", Role.PHARMACIST)
    client = APIClient()

    ok = client.post("/api/auth/token/", {"phone": "234567", "password": PASSWORD},
                     format="json", HTTP_X_TENANT_ID=a.slug)
    assert ok.status_code == 200, ok.content
    # The slug goes back as the header; the name is what the client shows.
    assert ok.json()["tenant"] == a.slug
    assert ok.json()["tenant_name"] == a.name
    # Same credentials against tenant B: no token, same opaque message.
    denied = client.post("/api/auth/token/", {"phone": "234567", "password": PASSWORD},
                         format="json", HTTP_X_TENANT_ID=b.slug)
    assert denied.status_code == 401, denied.content


def test_same_phone_suffix_allowed_in_different_tenants(tenants):
    from apps.accounts.models import Role
    from apps.accounts.serializers import UserSerializer

    a, b = tenants
    _staff(a, "08031111111", Role.PHARMACIST)
    s = UserSerializer(data={"phone": "08091111111", "role": Role.PHARMACIST,
                             "tenant": b.id, "password": PASSWORD})
    assert s.is_valid(), s.errors


def test_cashier_cannot_name_another_tenants_user(tenants):
    from apps.accounts.models import Role
    from apps.pos.serializers import CashierSerializer

    a, b = tenants
    outsider = _staff(b, "08037654321", Role.PHARMACIST)

    set_current_tenant(a)
    s = CashierSerializer(data={"user": outsider.id, "name": "Ade"})
    assert not s.is_valid()
    assert "user" in s.errors

    insider = _staff(a, "08031234567", Role.PHARMACIST)
    s = CashierSerializer(data={"user": insider.id, "name": "Ade"})
    assert s.is_valid(), s.errors
