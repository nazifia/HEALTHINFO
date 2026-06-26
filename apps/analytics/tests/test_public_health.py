"""Public-health rollups: AMR resistance rate and vital-registration mortality
ratios — the non-trivial rate math in stats.py."""
import pytest

from apps.analytics.models import (
    Appointment,
    CommunityHealthReport,
    FacilityMetric,
    Immunization,
    InsuranceClaim,
    LabResult,
    StockReport,
    VitalEvent,
)
from apps.analytics.stats import (
    appointment_stats,
    chw_stats,
    facility_stats,
    immunization_stats,
    insurance_stats,
    lab_stats,
    stock_stats,
    vital_stats,
)
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def test_amr_rate(db_clean):
    t = Tenant.objects.create(name="Lab", slug="lab")
    # 3 E. coli isolates tested vs ciprofloxacin: 2 resistant, 1 susceptible.
    LabResult.objects.create(tenant=t, organism="E. coli", antibiotic="cipro", susceptibility="resistant")
    LabResult.objects.create(tenant=t, organism="E. coli", antibiotic="cipro", susceptibility="resistant")
    LabResult.objects.create(tenant=t, organism="E. coli", antibiotic="cipro", susceptibility="susceptible")
    # A result with no AST must not enter the denominator.
    LabResult.objects.create(tenant=t, flag="normal")

    s = lab_stats(platform=True)
    assert (s["isolates_tested"], s["resistant"], s["amr_rate"]) == (3, 2, round(2 / 3, 4))
    by_org = {r["organism"]: r["resistance_rate"] for r in s["amr_by_organism"]}
    assert by_org["E. coli"] == round(2 / 3, 4)


def test_mortality_ratios(db_clean):
    t = Tenant.objects.create(name="Hosp", slug="hosp")
    for _ in range(4):
        VitalEvent.objects.create(tenant=t, event_type="birth")
    VitalEvent.objects.create(tenant=t, event_type="death", maternal_death=True)
    VitalEvent.objects.create(tenant=t, event_type="death", infant_death=True)

    s = vital_stats(platform=True)
    assert (s["births"], s["deaths"]) == (4, 2)
    # 1 maternal death / 4 births * 100000 ; 1 infant death / 4 births * 1000.
    assert s["maternal_mortality_ratio"] == 25000.0
    assert s["infant_mortality_rate"] == 250.0


def test_mortality_no_births_is_none(db_clean):
    t = Tenant.objects.create(name="H2", slug="h2")
    VitalEvent.objects.create(tenant=t, event_type="death", maternal_death=True)
    s = vital_stats(platform=True)
    assert s["maternal_mortality_ratio"] is None  # no denominator


def test_stock_shortage_and_consumption(db_clean):
    from apps.catalog.models import Medication

    t = Tenant.objects.create(name="Pharm", slug="pharm")
    para = Medication.objects.create(tenant=t, generic_name="Paracetamol", status="published")
    StockReport.objects.create(tenant=t, medication=para, on_hand=0, consumed=120, shortage=True)
    StockReport.objects.create(tenant=t, medication=para, on_hand=50, consumed=30)

    s = stock_stats(platform=True)
    assert s["shortage_count"] == 1
    assert s["top_consumed"][0]["consumed"] == 150


def test_immunization_coverage(db_clean):
    t = Tenant.objects.create(name="PHC", slug="phc")
    Immunization.objects.create(tenant=t, vaccine="BCG")
    Immunization.objects.create(tenant=t, vaccine="BCG")
    Immunization.objects.create(tenant=t, vaccine="Measles")

    s = immunization_stats(platform=True)
    assert s["total_doses"] == 3
    assert {r["vaccine"]: r["count"] for r in s["by_vaccine"]} == {"BCG": 2, "Measles": 1}


def test_chw_referral_rate(db_clean):
    t = Tenant.objects.create(name="CHW", slug="chw")
    CommunityHealthReport.objects.create(tenant=t, report_type="pregnancy", referred=True, danger_signs=True)
    CommunityHealthReport.objects.create(tenant=t, report_type="newborn", referred=True)
    CommunityHealthReport.objects.create(tenant=t, report_type="malnutrition")
    CommunityHealthReport.objects.create(tenant=t, report_type="malnutrition")

    s = chw_stats(platform=True)
    assert (s["total"], s["referred"], s["danger_signs"]) == (4, 2, 1)
    assert s["referral_rate"] == 0.5


def test_facility_occupancy(db_clean):
    t = Tenant.objects.create(name="Fac", slug="fac")
    FacilityMetric.objects.create(tenant=t, beds_total=100, beds_occupied=60, avg_wait_minutes=30, patients_treated=40)
    FacilityMetric.objects.create(tenant=t, beds_total=100, beds_occupied=80, avg_wait_minutes=50, patients_treated=60)

    s = facility_stats(platform=True)
    # (60+80) / (100+100) = 0.7 ; avg wait (30+50)/2 = 40 ; throughput 100.
    assert s["occupancy_rate"] == 0.7
    assert s["avg_wait_minutes"] == 40.0
    assert s["patients_treated"] == 100


def test_insurance_approval_rate(db_clean):
    t = Tenant.objects.create(name="Ins", slug="ins")
    InsuranceClaim.objects.create(tenant=t, amount=1000, status="approved")
    InsuranceClaim.objects.create(tenant=t, amount=2000, status="paid")
    InsuranceClaim.objects.create(tenant=t, amount=500, status="rejected")
    InsuranceClaim.objects.create(tenant=t, amount=300, status="submitted")  # undecided

    s = insurance_stats(platform=True)
    assert s["total_amount"] == 3800.0
    # 2 approved/paid of 3 decided (submitted excluded from denominator).
    assert s["approval_rate"] == round(2 / 3, 4)


def test_appointment_no_show_rate(db_clean):
    t = Tenant.objects.create(name="Appt", slug="appt")
    Appointment.objects.create(tenant=t, mode="telemedicine", status="completed")
    Appointment.objects.create(tenant=t, status="completed")
    Appointment.objects.create(tenant=t, status="no_show")
    Appointment.objects.create(tenant=t, status="scheduled")  # not yet due

    s = appointment_stats(platform=True)
    assert (s["total"], s["telemedicine"]) == (4, 1)
    # 1 no-show of 3 due (scheduled excluded).
    assert s["no_show_rate"] == round(1 / 3, 4)
