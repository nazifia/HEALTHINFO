"""The user list narrows to one organization, and never widens to another.

A platform admin runs one user list spanning every portal, so the sections
that hold an organization — a facility, a scheme, a health authority's patch —
each link to that list narrowed to their own people. The narrowing is a query
parameter, which means a scoped seat could send it too: it must only ever cut
into what that seat already saw.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def world(db):
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    one = Tenant.objects.create(name="One", slug="one-p", jurisdiction=lagos)
    two = Tenant.objects.create(name="Two", slug="two-p", jurisdiction=kano)
    staff = User.objects.create_user(phone="08030001001", password="x",
                                     role=Role.TENANT_ADMIN, tenant=one)
    other = User.objects.create_user(phone="08030001002", password="x",
                                     role=Role.PHARMACIST, tenant=two)
    gov = User.objects.create_user(phone="08030001003", password="x",
                                   role=Role.GOVERNMENT, jurisdiction=lagos)
    admin = User.objects.create_user(phone="08030001000", password="x",
                                     role=Role.SUPER_ADMIN)
    yield {"one": one, "two": two, "lagos": lagos, "kano": kano,
           "staff": staff, "other": other, "gov": gov, "admin": admin}
    clear_current_tenant()


def _client(user, tenant=""):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug if tenant else "")
    return c


def _phones(res):
    return {r["phone"] for r in res.json()["results"]}


def test_platform_admin_narrows_the_list_by_organization(world):
    c = _client(world["admin"])
    assert _phones(c.get("/api/users/", {"tenant": world["one"].pk})) == {"08030001001"}
    # The section links are a role narrowing, which is the same filter.
    assert _phones(c.get("/api/users/", {"role": Role.GOVERNMENT})) == {"08030001003"}


def test_a_state_pick_keeps_the_authority_seats_on_that_patch(world):
    """They staff no facility, so the state reaches them through their patch."""
    c = _client(world["admin"])
    assert _phones(c.get("/api/users/", {"jurisdiction": world["lagos"].pk})) == {
        "08030001001", "08030001003"}
    assert _phones(c.get("/api/users/", {"jurisdiction": world["kano"].pk})) == {"08030001002"}


def test_a_filter_cannot_widen_a_scoped_list(world):
    """Inside an organization the list is that organization's, filter or not.

    A platform admin who opened one facility reads its people; naming another
    facility in the filter narrows that list to nothing rather than widening it
    to the other's staff.
    """
    c = _client(world["admin"], world["one"])
    assert _phones(c.get("/api/users/")) == {"08030001001"}
    assert _phones(c.get("/api/users/", {"tenant": world["two"].pk})) == set()
