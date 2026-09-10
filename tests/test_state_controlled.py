"""Controlled (poison) drugs prescribed and dispensed, folded up to the state.

Two things the regulator's number has to get right: only flagged items count,
and "dispensed" is the subset actually handed over — never the whole script.
"""
import pytest
from decimal import Decimal
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.stats import platform_controlled_stats
from apps.inventory.models import StockItem
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def scripts(db):
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    ikeja = Jurisdiction.objects.create(name="Ikeja", level="local", parent=lagos)
    nass = Jurisdiction.objects.create(name="Nassarawa", level="local", parent=kano)
    lag = Tenant.objects.create(name="Ikeja Pharmacy", slug="ikeja-c", jurisdiction=ikeja)
    kan = Tenant.objects.create(name="Nassarawa Pharmacy", slug="nass-c", jurisdiction=nass)

    def item(tenant, name, controlled):
        return StockItem.all_objects.create(
            tenant=tenant, name=name, unit="tablet", is_controlled=controlled,
            cost_price=Decimal("10.00"), unit_price=Decimal("50.00"),
        )

    codeine = item(lag, "Codeine syrup", True)
    tramadol = item(lag, "Tramadol 100mg", True)
    para = item(lag, "Paracetamol 500mg", False)
    kano_codeine = item(kan, "Codeine syrup", True)

    def line(tenant, stock, qty, dispensed):
        rx = Prescription.all_objects.create(tenant=tenant, customer_name="Walk-in")
        return PrescriptionItem.all_objects.create(
            tenant=tenant, prescription=rx, item=stock, name=stock.name,
            quantity=qty, is_dispensed=dispensed,
        )

    line(lag, codeine, 2, True)
    line(lag, codeine, 3, False)     # written for, never handed over
    line(lag, tramadol, 10, True)
    line(lag, para, 100, True)       # not controlled: not in the register
    line(kan, kano_codeine, 4, True)
    yield {"lagos": lagos, "kano": kano, "ikeja": ikeja}
    clear_current_tenant()


def _areas(stats):
    return {r[stats["level"]]: r for r in stats["by_area"]}


def test_only_controlled_lines_count_and_dispensed_is_the_handed_over_subset(scripts):
    stats = platform_controlled_stats()
    assert stats["level"] == "state"
    areas = _areas(stats)
    # 3 controlled lines in Lagos (15 units); the paracetamol is not one of them.
    assert areas["Lagos"]["prescribed"] == 3
    assert areas["Lagos"]["prescribed_units"] == 15
    # One codeine line was never handed over: 2 lines, 12 units.
    assert areas["Lagos"]["dispensed"] == 2
    assert areas["Lagos"]["dispensed_units"] == 12
    assert areas["Kano"]["prescribed"] == 1
    assert areas["Kano"]["dispensed_units"] == 4


def test_by_drug_names_the_molecule(scripts):
    by_drug = {r["drug"]: r for r in platform_controlled_stats()["by_drug"]}
    assert "Paracetamol 500mg" not in by_drug
    assert by_drug["Codeine syrup"]["prescribed"] == 3       # Lagos 2 + Kano 1
    assert by_drug["Codeine syrup"]["dispensed_units"] == 6  # 2 + 4
    assert by_drug["Tramadol 100mg"]["prescribed_units"] == 10


def test_a_state_seat_reads_its_own_patch_only(scripts):
    stats = platform_controlled_stats(jurisdiction=scripts["lagos"])
    assert [r["state"] for r in stats["by_area"]] == ["Lagos"]
    # Ordered by lines written: codeine twice, tramadol once, and no Kano row.
    assert [r["drug"] for r in stats["by_drug"]] == ["Codeine syrup",
                                                     "Tramadol 100mg"]
    assert stats["by_drug"][0]["dispensed_units"] == 2


def test_a_local_seat_is_not_told_its_state_total(scripts):
    stats = platform_controlled_stats(jurisdiction=scripts["ikeja"])
    assert stats["level"] == "local"
    assert [r["local"] for r in stats["by_area"]] == ["Ikeja"]


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID="")
    return c


def test_only_the_authority_and_the_platform_admin_read_it(scripts, db):
    gov = User.objects.create_user(phone="08030000801", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=scripts["lagos"])
    admin = User.objects.create_user(phone="08030000802", password="x",
                                     role=Role.SUPER_ADMIN)
    pharmacist = User.objects.create_user(
        phone="08030000803", password="x", role=Role.PHARMACIST,
        tenant=Tenant.objects.get(slug="ikeja-c"),
    )
    url = "/api/analytics/platform/controlled/"
    res = _client(gov).get(url)
    assert res.status_code == 200
    assert [r["state"] for r in res.json()["by_area"]] == ["Lagos"]
    assert _client(admin).get(url).status_code == 200
    assert _client(pharmacist).get(url).status_code == 403


def test_csv_carries_areas_and_drugs(scripts, db):
    gov = User.objects.create_user(phone="08030000804", password="x",
                                   role=Role.GOVERNMENT,
                                   jurisdiction=scripts["lagos"])
    res = _client(gov).get("/api/analytics/platform/controlled/", {"format": "csv"})
    assert res.status_code == 200
    assert res["Content-Type"] == "text/csv"
    lines = res.content.decode().splitlines()
    assert lines[0] == ("bucket,name,prescribed,prescribed_units,dispensed,"
                        "dispensed_units")
    assert lines[1] == "area,Lagos,3,15,2,12"
    assert [line.split(",")[0] for line in lines[2:]] == ["drug", "drug"]
