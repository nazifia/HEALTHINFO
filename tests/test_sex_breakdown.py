"""Every patient-linked rollup splits its rows by the patient's sex."""
import pytest

from apps.analytics import stats
from apps.analytics.models import (
    AdverseDrugReaction, Appointment, CaseReport, Immunization, Prescription,
)
from apps.catalog.models import Medication
from apps.patients.models import Patient
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def rows(db):
    t = Tenant.objects.create(name="Clinic", slug="sex-t")
    her = Patient.all_objects.create(tenant=t, first_name="A", last_name="B", sex="F")
    him = Patient.all_objects.create(tenant=t, first_name="C", last_name="D", sex="M")
    med = Medication.objects.create(generic_name="Paracetamol")
    for p in (her, her, him):
        CaseReport.all_objects.create(tenant=t, patient=p)
        Appointment.all_objects.create(tenant=t, patient=p)
        Immunization.all_objects.create(tenant=t, patient=p, vaccine="BCG")
        Prescription.all_objects.create(tenant=t, patient=p, medication=med)
        AdverseDrugReaction.all_objects.create(
            tenant=t, patient=p, medication=med, reaction="rash")
    CaseReport.all_objects.create(tenant=t)  # no patient: sex unrecorded
    yield
    clear_current_tenant()


def _sex(rows):
    return {r["sex"]: r["count"] for r in rows}


def test_rows_split_by_the_patients_sex(rows):
    assert _sex(stats.platform_case_report_stats()["by_sex"]) == {
        "F": 2, "M": 1, "unknown": 1}
    assert _sex(stats.appointment_stats(platform=True)["by_sex"]) == {"F": 2, "M": 1}
    assert _sex(stats.immunization_stats(platform=True)["by_sex"]) == {"F": 2, "M": 1}
    assert _sex(stats.prescription_stats(platform=True)["by_sex"]) == {"F": 2, "M": 1}
    assert _sex(stats.adr_stats(platform=True)["by_sex"]) == {"F": 2, "M": 1}
