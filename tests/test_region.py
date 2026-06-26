"""Region = "LGA, State" from the Nigeria list: validated on write, rolled up
to state in the breakdown."""
import pytest

from apps.analytics.models import CaseReport
from apps.analytics.nigeria import region_state, valid_regions
from apps.analytics.serializers import CaseReportSerializer
from apps.analytics.stats import case_report_stats
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_region_state_parses_lga_state():
    assert region_state("Ikeja, Lagos") == "Lagos"
    assert region_state("garbage") == ""


def test_known_regions_validate_and_typos_reject():
    assert "Ikeja, Lagos" in valid_regions()
    assert CaseReportSerializer().validate_region("Ikeja, Lagos") == "Ikeja, Lagos"
    assert CaseReportSerializer().validate_region("") == ""  # optional
    with pytest.raises(Exception):
        CaseReportSerializer().validate_region("Nowhere, Atlantis")


def test_breakdown_rolls_region_up_to_state(tenant):
    CaseReport.objects.create(severity="mild", region="Ikeja, Lagos")
    CaseReport.objects.create(severity="mild", region="Epe, Lagos")
    CaseReport.objects.create(severity="mild", region="Bende, Abia")
    by_state = {r["state"]: r["count"] for r in case_report_stats()["by_region_state"]}
    assert by_state == {"Lagos": 2, "Abia": 1}
