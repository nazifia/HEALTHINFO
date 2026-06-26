"""Staff file case reports; the platform view collates them across all tenants."""
import pytest

from apps.analytics.models import CaseReport
from apps.analytics.stats import (
    benchmark_stats,
    case_report_stats,
    platform_case_report_stats,
)
from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenants(db):
    a = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    b = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    yield a, b
    clear_current_tenant()


def test_reports_are_tenant_scoped_but_collate_centrally(tenants):
    a, b = tenants

    set_current_tenant(a)
    malaria = Disease.objects.create(name="Malaria", slug="malaria")
    CaseReport.objects.create(disease=malaria, severity="severe", outcome="recovered")
    CaseReport.objects.create(disease=malaria, severity="mild")

    set_current_tenant(b)
    cholera = Disease.objects.create(name="Cholera", slug="cholera")
    CaseReport.objects.create(disease=cholera, severity="critical", outcome="referred")

    # Each tenant only rolls up its own reports.
    set_current_tenant(a)
    assert case_report_stats()["total"] == 2
    set_current_tenant(b)
    assert case_report_stats()["total"] == 1

    # Central collation sees every tenant's cases for analysis.
    clear_current_tenant()
    platform = platform_case_report_stats()
    assert platform["total"] == 3
    by_tenant = {r["tenant__name"]: r["count"] for r in platform["by_tenant"]}
    assert by_tenant == {"Hospital A": 2, "Hospital B": 1}


def test_benchmark_ignores_global_rows(tenants):
    a, b = tenants

    set_current_tenant(a)
    CaseReport.objects.create(severity="mild")
    CaseReport.objects.create(severity="mild")
    set_current_tenant(b)
    CaseReport.objects.create(severity="mild")
    # Global row (tenant=None) — must not count as a tenant in the comparison.
    clear_current_tenant()
    CaseReport.all_objects.create(tenant=None, severity="mild")

    set_current_tenant(a)
    stats = benchmark_stats()
    assert stats["your_case_reports"] == 2
    assert stats["tenants_compared"] == 2  # A and B only, not the global row
    assert stats["platform_median"] == 1.5  # median(2, 1), no phantom None bucket
