"""A platform admin picks a state and every cross-tenant read follows it.

The state arrives as X-Jurisdiction-ID. It narrows the rollups, the facility
list they open a tenant from and the user list — government level down to the
facility whose patients they then read. A health authority seat can drill into
its own patch with the same header but never sideways out of it.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def country(db):
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    ikeja = Jurisdiction.objects.create(name="Ikeja", level="local", parent=lagos)
    nassarawa = Jurisdiction.objects.create(name="Nassarawa", level="local", parent=kano)
    lag = Tenant.objects.create(name="Ikeja Clinic", slug="ikeja-p", jurisdiction=ikeja)
    kan = Tenant.objects.create(name="Nassarawa Clinic", slug="nass-p", jurisdiction=nassarawa)
    for _ in range(2):
        CaseReport.all_objects.create(tenant=lag)
    CaseReport.all_objects.create(tenant=kan)
    User.objects.create_user(phone="08030000601", password="x",
                             role=Role.PHARMACIST, tenant=lag)
    User.objects.create_user(phone="08030000602", password="x",
                             role=Role.PHARMACIST, tenant=kan)
    yield {"nation": nation, "lagos": lagos, "kano": kano, "ikeja": ikeja}
    clear_current_tenant()


def _client(user, jurisdiction=None):
    c = APIClient()
    c.force_authenticate(user=user)
    extra = {"HTTP_X_TENANT_ID": ""}
    if jurisdiction is not None:
        extra["HTTP_X_JURISDICTION_ID"] = str(jurisdiction.pk)
    c.credentials(**extra)
    return c


@pytest.fixture
def admin(db):
    return User.objects.create_user(phone="08030000600", password="x",
                                    role=Role.SUPER_ADMIN)


def test_picking_a_state_narrows_the_rollup(country, admin):
    assert _client(admin).get("/api/analytics/platform/cases/").json()["total"] == 3
    res = _client(admin, country["lagos"]).get("/api/analytics/platform/cases/")
    assert res.json()["total"] == 2
    assert [r["state"] for r in res.json()["by_state"]] == ["Lagos"]


def test_picking_a_state_narrows_the_facility_and_user_lists(country, admin):
    picked = _client(admin, country["lagos"])
    tenants = picked.get("/api/tenants/").json()["results"]
    assert [t["name"] for t in tenants] == ["Ikeja Clinic"]
    phones = {u["phone"] for u in picked.get("/api/users/").json()["results"]}
    assert phones == {"08030000601"}


def test_a_local_government_pick_narrows_further(country, admin):
    res = _client(admin, country["ikeja"]).get("/api/analytics/platform/cases/")
    assert res.json()["total"] == 2
    assert "by_state" not in res.json()


def test_no_pick_is_still_the_whole_country(country, admin):
    tenants = _client(admin).get("/api/tenants/").json()["results"]
    assert len(tenants) == 2


def test_a_state_seat_cannot_pick_another_state(country):
    gov = User.objects.create_user(phone="08030000603", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=country["kano"])
    res = _client(gov, country["lagos"]).get("/api/analytics/platform/cases/")
    assert res.json()["total"] == 1
    assert [r["state"] for r in res.json()["by_state"]] == ["Kano"]


def test_a_state_seat_may_drill_into_its_own_patch(country):
    nassarawa = Jurisdiction.objects.get(name="Nassarawa")
    gov = User.objects.create_user(phone="08030000604", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=country["kano"])
    res = _client(gov, nassarawa).get("/api/analytics/platform/cases/")
    assert res.json()["total"] == 1
    assert "by_state" not in res.json()


def test_a_bad_pick_is_ignored_not_obeyed(country, admin):
    c = APIClient()
    c.force_authenticate(user=admin)
    c.credentials(HTTP_X_TENANT_ID="", HTTP_X_JURISDICTION_ID="not-a-number")
    assert c.get("/api/analytics/platform/cases/").json()["total"] == 3
