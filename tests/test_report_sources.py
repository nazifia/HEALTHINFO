"""Report sources pool both report streams and collate across tenants."""
import pytest

from apps.accounts.models import User
from apps.analytics.models import AdverseDrugReaction, CaseReport
from apps.analytics.stats import report_sources
from apps.catalog.models import Medication
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenants(db):
    a = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    b = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    yield a, b
    clear_current_tenant()


def test_sources_pool_cases_and_adrs_across_tenants(tenants):
    a, b = tenants

    set_current_tenant(a)
    nurse = User.objects.create_user(phone="08031234567", password="x", username="nurse")
    drug = Medication.objects.create(generic_name="Paracetamol")
    CaseReport.objects.create(reporter=nurse, region="Lagos", severity="mild")
    AdverseDrugReaction.objects.create(
        reporter=nurse, medication=drug, reaction="rash", region="Lagos"
    )

    set_current_tenant(b)
    CaseReport.objects.create(region="Abuja", severity="severe")

    # Tenant scope: A sees only its own two reports (1 case + 1 ADR).
    set_current_tenant(a)
    mine = report_sources()
    assert mine["total_cases"] == 1
    assert mine["total_adrs"] == 1
    # Both streams merge under the same region.
    assert {r["region"]: r["count"] for r in mine["by_region"]} == {"Lagos": 2}
    assert {r["reporter__username"]: r["count"] for r in mine["by_reporter"]} == {
        "nurse": 2
    }
    assert "by_tenant" not in mine  # tenant view has no cross-tenant breakdown

    # Platform: collates every tenant's reports and keys origin by tenant.
    clear_current_tenant()
    plat = report_sources(platform=True)
    assert plat["total_cases"] == 2
    assert plat["total_adrs"] == 1
    assert {r["tenant__name"]: r["count"] for r in plat["by_tenant"]} == {
        "Hospital A": 2,
        "Hospital B": 1,
    }
