"""Central collation folds tenant cases up the gov hierarchy: local → state."""
import pytest

from apps.analytics.models import AdverseDrugReaction, CaseReport
from apps.analytics.stats import adr_stats, platform_case_report_stats
from apps.catalog.models import Disease, Medication
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def hierarchy(db):
    # central → state → two locals, a tenant under each local.
    nation = Jurisdiction.objects.create(name="Nigeria", level="national")
    lagos = Jurisdiction.objects.create(name="Lagos", level="state", parent=nation)
    kano = Jurisdiction.objects.create(name="Kano", level="state", parent=nation)
    ikeja = Jurisdiction.objects.create(name="Ikeja", level="local", parent=lagos)
    nassarawa = Jurisdiction.objects.create(name="Nassarawa", level="local", parent=kano)
    a = Tenant.objects.create(name="Clinic A", slug="a", jurisdiction=ikeja)
    b = Tenant.objects.create(name="Clinic B", slug="b", jurisdiction=nassarawa)
    yield a, b
    clear_current_tenant()


def test_ancestor_walk():
    nation = Jurisdiction(name="N", level="national")
    state = Jurisdiction(name="S", level="state", parent=nation)
    local = Jurisdiction(name="L", level="local", parent=state)
    assert local.ancestor("state") is state
    assert local.ancestor("national") is nation
    assert state.ancestor("local") is None  # no descending


def test_platform_rollup_folds_to_state(hierarchy):
    a, b = hierarchy
    set_current_tenant(a)
    mal = Disease.objects.create(name="Malaria", slug="malaria")
    CaseReport.objects.create(disease=mal, severity="severe")
    CaseReport.objects.create(disease=mal, severity="mild")
    set_current_tenant(b)
    chol = Disease.objects.create(name="Cholera", slug="cholera")
    CaseReport.objects.create(disease=chol, severity="mild")

    clear_current_tenant()
    stats = platform_case_report_stats()
    by_state = {r["state"]: r["count"] for r in stats["by_state"]}
    by_local = {r["local"]: r["count"] for r in stats["by_local"]}
    assert by_state == {"Lagos": 2, "Kano": 1}
    assert by_local == {"Ikeja": 2, "Nassarawa": 1}


def test_platform_adr_rollup_folds_to_state(hierarchy):
    a, b = hierarchy
    set_current_tenant(a)
    drug = Medication.objects.create(generic_name="Amoxicillin")
    AdverseDrugReaction.objects.create(medication=drug, reaction="rash")
    set_current_tenant(b)
    drug_b = Medication.objects.create(generic_name="Penicillin")
    AdverseDrugReaction.objects.create(medication=drug_b, reaction="anaphylaxis")
    AdverseDrugReaction.objects.create(medication=drug_b, reaction="hives")

    clear_current_tenant()
    stats = adr_stats(platform=True)
    by_state = {r["state"]: r["count"] for r in stats["by_state"]}
    by_local = {r["local"]: r["count"] for r in stats["by_local"]}
    assert by_state == {"Lagos": 1, "Kano": 2}
    assert by_local == {"Ikeja": 1, "Nassarawa": 2}
