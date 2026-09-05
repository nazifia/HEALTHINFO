"""IDSR weekly summary: epi-week grouping, deaths and case-fatality rate, the
national-tier collation, and the 24-hour immediate-notification worklist."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analytics.idsr import (
    immediate_alerts,
    platform_idsr_report,
    weekly_summary,
)
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
        name="Cholera", icd10_code="A00", notifiable=True,
        notify_immediately=True, status="published",
    )

    # 4 cases this week, 1 deceased → CFR 0.25.
    CaseReport.objects.create(tenant=tenant, disease=cholera, outcome="deceased")
    for _ in range(3):
        CaseReport.objects.create(tenant=tenant, disease=cholera, outcome="recovered")

    [row] = weekly_summary(CaseReport.all_objects.all())
    assert row["disease"] == "Cholera"
    assert row["notifiable"] is True
    assert row["notify_immediately"] is True
    assert (row["cases"], row["deaths"], row["case_fatality_rate"]) == (4, 1, 0.25)
    assert row["epi_week"].startswith("20") and "-W" in row["epi_week"]

    # Central collation reaches the national apex.
    report = platform_idsr_report()
    assert {r["national"]: r["count"] for r in report["by_national"]} == {"NG": 4}


def test_immediate_alerts_lists_only_the_24_hour_diseases(db_clean):
    """Immediately-notifiable cases are listed one by one; weekly ones are not.

    Also pins the deadline: a case filed 30 hours ago is overdue even though a
    72-hour window is what surfaced it.
    """
    tenant = Tenant.objects.create(name="Clinic B", slug="b")
    cholera = Disease.objects.create(
        name="Cholera", slug="cholera", icd10_code="A00", notifiable=True,
        notify_immediately=True, status="published",
    )
    # Notifiable but weekly, not immediate — must stay out of the worklist.
    tb = Disease.objects.create(
        name="Tuberculosis", slug="tb", icd10_code="A15", notifiable=True,
        status="published",
    )
    fresh = CaseReport.objects.create(tenant=tenant, disease=cholera)
    stale = CaseReport.objects.create(tenant=tenant, disease=cholera)
    CaseReport.objects.create(tenant=tenant, disease=tb)
    # auto_now_add ignores an assigned value, so age the row after insert.
    CaseReport.all_objects.filter(pk=stale.pk).update(
        created_at=timezone.now() - timedelta(hours=30)
    )

    # Default 24-hour window sees only the fresh case.
    [row] = immediate_alerts(CaseReport.all_objects.all())
    assert (row["id"], row["disease"], row["overdue"]) == (fresh.pk, "Cholera", False)

    # Widening the window surfaces the missed one, oldest first, marked overdue.
    rows = immediate_alerts(CaseReport.all_objects.all(), hours=72)
    assert [r["id"] for r in rows] == [stale.pk, fresh.pk]
    assert rows[0]["overdue"] is True and rows[0]["hours_elapsed"] >= 30
