"""report_sources jurisdiction rollup: two tenants under one state fold up."""
import pytest

from apps.analytics.models import AdverseDrugReaction, CaseReport
from apps.analytics.stats import report_sources
from apps.catalog.models import Medication
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def test_report_sources_folds_two_tenants_into_one_state(db_clean):
    national = Jurisdiction.objects.create(name="NG", level="national")
    state = Jurisdiction.objects.create(name="Lagos", level="state", parent=national)
    lga_a = Jurisdiction.objects.create(name="Ikeja", level="local", parent=state)
    lga_b = Jurisdiction.objects.create(name="Surulere", level="local", parent=state)

    t_a = Tenant.objects.create(name="Clinic A", slug="a", jurisdiction=lga_a)
    t_b = Tenant.objects.create(name="Clinic B", slug="b", jurisdiction=lga_b)
    med = Medication.objects.create(generic_name="Paracetamol", status="published")

    # 2 case reports under A, 1 ADR under B — all same state.
    CaseReport.objects.create(tenant=t_a)
    CaseReport.objects.create(tenant=t_a)
    AdverseDrugReaction.objects.create(tenant=t_b, medication=med, reaction="rash")

    out = report_sources(platform=True)

    by_state = {r["state"]: r["count"] for r in out["by_state"]}
    by_local = {r["local"]: r["count"] for r in out["by_local"]}
    assert by_state == {"Lagos": 3}           # 2 cases + 1 ADR summed
    assert by_local == {"Ikeja": 2, "Surulere": 1}
