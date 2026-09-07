"""A health authority seat reads its own patch and nobody else's.

Jurisdiction and Tenant.jurisdiction always existed, and the rollups always
folded up to a tier — but nothing narrowed a seat down to one, so a Kano
authority was answered with Lagos rows. These are the checks that fail if that
narrowing comes undone.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.analytics.stats import platform_case_report_stats, platform_stats
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def country(db):
    """Two states, one tenant each, two Lagos cases against one Kano case."""
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    ikeja = Jurisdiction.objects.create(name="Ikeja", level="local", parent=lagos)
    nassarawa = Jurisdiction.objects.create(name="Nassarawa", level="local", parent=kano)
    lag_tenant = Tenant.objects.create(name="Ikeja Clinic", slug="ikeja-j",
                                       jurisdiction=ikeja)
    kan_tenant = Tenant.objects.create(name="Nassarawa Clinic", slug="nass-j",
                                       jurisdiction=nassarawa)
    for _ in range(2):
        CaseReport.all_objects.create(tenant=lag_tenant)
    CaseReport.all_objects.create(tenant=kan_tenant)
    yield nation, kano, lagos, kan_tenant
    clear_current_tenant()


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID="")
    return c


def test_subtree_reaches_both_tiers_below_and_no_sideways(country):
    nation, kano, lagos, _ = country
    assert {j.name for j in kano.subtree()} == {"Kano", "Nassarawa"}
    assert {j.name for j in nation.subtree()} == {
        "Nigeria", "Lagos", "Kano", "Ikeja", "Nassarawa"
    }
    assert "Lagos" not in {j.name for j in kano.subtree()}


def test_a_kano_seat_is_not_answered_with_lagos_rows(country):
    _, kano, _, _ = country
    stats = platform_case_report_stats(jurisdiction=kano)
    assert stats["total"] == 1
    assert [r["state"] for r in stats["by_state"]] == ["Kano"]
    assert [r["tenant__name"] for r in stats["by_tenant"]] == ["Nassarawa Clinic"]
    # Facility and staff counts narrow with it — one clinic in Kano, not two.
    assert platform_stats(jurisdiction=kano)["total_tenants"] == 1


def test_a_seat_is_not_offered_a_tier_above_its_own(country):
    """Kano's rows folded to national would print as Nigeria's total."""
    _, kano, _, _ = country
    stats = platform_case_report_stats(jurisdiction=kano)
    assert "by_national" not in stats
    assert [r["state"] for r in stats["by_state"]] == ["Kano"]
    assert [r["local"] for r in stats["by_local"]] == ["Nassarawa"]

    # A local seat keeps only its own tier; state and national both overstate.
    nassarawa = Jurisdiction.objects.get(name="Nassarawa")
    local_seat = platform_case_report_stats(jurisdiction=nassarawa)
    assert "by_state" not in local_seat and "by_national" not in local_seat
    assert [r["local"] for r in local_seat["by_local"]] == ["Nassarawa"]


def test_the_centre_still_gets_every_tier(country):
    nation, _, _, _ = country
    for stats in (platform_case_report_stats(),
                  platform_case_report_stats(jurisdiction=nation)):
        assert {r["national"]: r["count"] for r in stats["by_national"]} == {
            "Nigeria": 3
        }
        assert {r["state"] for r in stats["by_state"]} == {"Kano", "Lagos"}


def test_no_jurisdiction_still_means_the_whole_country(country):
    assert platform_case_report_stats()["total"] == 3
    assert platform_stats()["total_tenants"] == 2


def test_the_seat_only_reaches_its_own_patch_over_the_api(country):
    _, kano, _, _ = country
    gov = User.objects.create_user(phone="08030000501", password="x",
                                   role=Role.GOVERNMENT, jurisdiction=kano)
    res = _client(gov).get("/api/analytics/platform/cases/")
    assert res.status_code == 200
    assert res.json()["total"] == 1


def test_a_seat_with_no_jurisdiction_reads_nothing(country):
    """Fail closed: no patch to answer for means no rollup, not every rollup."""
    gov = User.objects.create_user(phone="08030000502", password="x",
                                   role=Role.GOVERNMENT)
    client = _client(gov)
    for path in ("/api/analytics/platform/", "/api/analytics/platform/cases/",
                 "/api/analytics/platform/surveillance/"):
        assert client.get(path).status_code == 403, path
