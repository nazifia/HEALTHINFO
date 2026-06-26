"""IDSR weekly summary: epi-week grouping, deaths and case-fatality rate, and
the national-tier collation."""
import pytest

from apps.analytics.idsr import platform_idsr_report, weekly_summary
from apps.analytics.models import CaseReport
from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def test_weekly_summary_cfr_and_national_rollup(db_clean):
    national = Jurisdiction.objects.create(name="NG", level="national")
    state = Jurisdiction.objects.create(name="Lagos", level="state", parent=national)
    lga = Jurisdiction.objects.create(name="Ikeja", level="local", parent=state)
    tenant = Tenant.objects.create(name="Clinic A", slug="a", jurisdiction=lga)
    cholera = Disease.objects.create(
        name="Cholera", icd10_code="A00", notifiable=True, status="published"
    )

    # 4 cases this week, 1 deceased → CFR 0.25.
    CaseReport.objects.create(tenant=tenant, disease=cholera, outcome="deceased")
    for _ in range(3):
        CaseReport.objects.create(tenant=tenant, disease=cholera, outcome="recovered")

    [row] = weekly_summary(CaseReport.all_objects.all())
    assert row["disease"] == "Cholera"
    assert row["notifiable"] is True
    assert (row["cases"], row["deaths"], row["case_fatality_rate"]) == (4, 1, 0.25)
    assert row["epi_week"].startswith("20") and "-W" in row["epi_week"]

    # Central collation reaches the national apex.
    report = platform_idsr_report()
    assert {r["national"]: r["count"] for r in report["by_national"]} == {"NG": 4}
