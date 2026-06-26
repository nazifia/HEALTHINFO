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
