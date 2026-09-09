"""Takings folded up to the state, for the authority that answers for it.

Money, unlike the surveillance rollups, has to net off what came back and
leave out what was never earned — so those two rules are what these check.
"""
import pytest
from decimal import Decimal
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.stats import platform_sales_stats
from apps.inventory.models import StockItem
from apps.pos.models import ReturnRecord, Sale, SaleItem
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def country(db):
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    ikeja = Jurisdiction.objects.create(name="Ikeja", level="local", parent=lagos)
    nass = Jurisdiction.objects.create(name="Nassarawa", level="local", parent=kano)
    lag = Tenant.objects.create(name="Ikeja Pharmacy", slug="ikeja-s", jurisdiction=ikeja)
    kan = Tenant.objects.create(name="Nassarawa Pharmacy", slug="nass-s", jurisdiction=nass)

    def sale(tenant, total, status=Sale.Status.PAID):
        return Sale.all_objects.create(tenant=tenant, total=total, status=status)

    sale(lag, Decimal("1000.00"))
    lag_second = sale(lag, Decimal("500.00"))
    sale(lag, Decimal("9999.00"), status=Sale.Status.CANCELLED)  # never happened
    sale(lag, Decimal("400.00"), status=Sale.Status.CREDIT)      # not paid for
    sale(kan, Decimal("250.00"))

    item = StockItem.all_objects.create(
        tenant=lag, name="Paracetamol 500mg", sku="PARA500", unit="tablet",
        cost_price=Decimal("100.00"), unit_price=Decimal("500.00"),
    )
    line = SaleItem.all_objects.create(
        tenant=lag, sale=lag_second, item=item, name="Paracetamol", quantity=1,
        unit_price=Decimal("500.00"),
    )
    ReturnRecord.all_objects.create(
        tenant=lag, sale=lag_second, line=line, quantity=1,
        amount=Decimal("200.00"),
    )
    yield {"lagos": lagos, "kano": kano, "ikeja": ikeja, "nation": nation}
    clear_current_tenant()


def _rows(stats, bucket):
    return {r[stats["level"]]: r for r in stats[bucket]}


def test_state_totals_net_refunds_and_skip_unearned_sales(country):
    stats = platform_sales_stats()
    assert stats["level"] == "state"
    daily = _rows(stats, "daily")
    # 1000 + 500 paid, less the 200 that came back. The cancelled and credit
    # sales are not takings at all.
    assert daily["Lagos"]["revenue"] == Decimal("1300.00")
    assert daily["Lagos"]["sales"] == 2
    assert daily["Kano"]["revenue"] == Decimal("250.00")
    # Same money, three window sizes: one day inside one month inside one year.
    for bucket, width in (("daily", 10), ("monthly", 7), ("yearly", 4)):
        rows = _rows(stats, bucket)
        assert rows["Lagos"]["revenue"] == Decimal("1300.00")
        assert len(rows["Lagos"]["period"]) == width


def test_a_state_seat_reads_its_own_patch_only(country):
    stats = platform_sales_stats(jurisdiction=country["lagos"])
    assert [r["state"] for r in stats["daily"]] == ["Lagos"]


def test_a_local_seat_is_not_told_its_state_total(country):
    stats = platform_sales_stats(jurisdiction=country["ikeja"])
    assert stats["level"] == "local"
    assert [r["local"] for r in stats["daily"]] == ["Ikeja"]


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID="")
    return c


def test_only_the_authority_and_the_platform_admin_read_it(country, db):
    gov = User.objects.create_user(phone="08030000701", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=country["lagos"])
    admin = User.objects.create_user(phone="08030000702", password="x",
                                     role=Role.SUPER_ADMIN)
    pharmacist = User.objects.create_user(
        phone="08030000703", password="x", role=Role.PHARMACIST,
        tenant=Tenant.objects.get(slug="ikeja-s"),
    )
    url = "/api/analytics/platform/sales/"
    res = _client(gov).get(url)
    assert res.status_code == 200
    assert [r["state"] for r in res.json()["daily"]] == ["Lagos"]
    assert _client(admin).get(url).status_code == 200
    assert _client(pharmacist).get(url).status_code == 403


def test_csv_carries_all_three_grains(country, db):
    gov = User.objects.create_user(phone="08030000704", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=country["lagos"])
    res = _client(gov).get("/api/analytics/platform/sales/", {"format": "csv"})
    assert res.status_code == 200
    assert res["Content-Type"] == "text/csv"
    lines = res.content.decode().splitlines()
    assert lines[0] == "bucket,state,period,revenue,sales"
    buckets = [line.split(",")[0] for line in lines[1:]]
    assert buckets == ["daily", "monthly", "yearly"]
    assert all(line.endswith("Lagos," + line.split(",")[2] + ",1300.00,2")
               for line in lines[1:])
