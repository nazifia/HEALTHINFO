"""Every facility — hospital or pharmacy — has somewhere to dispense from."""
import pytest

from apps.branches.models import Branch, ensure_pharmacy
from apps.tenants.models import Tenant


def test_hospital_gets_its_own_pharmacy(db):
    tenant = Tenant.objects.create(
        name="St Mary's", slug="st-marys", kind=Tenant.Kind.HOSPITAL
    )
    branch = Branch.all_objects.get(tenant=tenant)
    assert branch.is_main
    assert branch.name == "St Mary's Pharmacy"


def test_pharmacy_tenant_gets_its_shop(db):
    tenant = Tenant.objects.create(name="Corner Chemist", slug="corner")
    branch = Branch.all_objects.get(tenant=tenant)
    assert branch.is_main and branch.name == "Corner Chemist"


def test_ensure_pharmacy_is_idempotent(db):
    tenant = Tenant.objects.create(
        name="Ikeja General", slug="ikeja-gen", kind=Tenant.Kind.HOSPITAL
    )
    first = ensure_pharmacy(tenant)
    again = ensure_pharmacy(tenant)
    assert first.pk == again.pk
    assert Branch.all_objects.filter(tenant=tenant).count() == 1


def test_existing_main_branch_is_left_alone(db):
    tenant = Tenant.objects.create(name="Two Shop", slug="two-shop")
    main = Branch.all_objects.get(tenant=tenant)
    main.name = "Head Office"
    main.save()
    assert ensure_pharmacy(tenant).pk == main.pk
