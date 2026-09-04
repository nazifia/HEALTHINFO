"""Dispensing reaches the data centre on its own.

What the counter does — the diagnosis on the script and the drugs handed over —
has to land in apps.analytics without anyone re-typing it, once for the
tenant's own dashboard and once, through the same row, for central collation.
The checks that matter are the ones where a bug loses or doubles a case: a
script filled twice must stay one case, a hospital's own order must not be
filed a second time by its pharmacy, and a box of gloves must never become a
drug the country thinks it prescribed.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport, Prescription as SurveillanceRx
from apps.analytics.stats import prescription_stats
from apps.catalog.models import Disease, Medication
from apps.inventory.models import StockItem, Store, receive_stock
from apps.patients.models import Patient
from apps.pos.models import Sale
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def _stocked(tenant, name, medication=None, quantity=50):
    item = StockItem.all_objects.create(
        tenant=tenant, name=name, medication=medication, unit="unit",
        cost_price=Decimal("10.00"), unit_price=Decimal("25.00"),
        store=Store.RETAIL,
    )
    receive_stock(item, quantity, batch_number=f"B-{item.pk}",
                  expiry_date=timezone.localdate() + timedelta(days=200),
                  cost_price=Decimal("10.00"))
    return item


@pytest.fixture
def counter(db_clean):
    """A pharmacy holding one catalogued drug and one consumable, plus a script."""
    tenant = Tenant.objects.create(name="Bola Pharmacy", slug="bola-dc")
    staff = User.objects.create_user(phone="08030000401", password="x",
                                     tenant=tenant, role=Role.PHARMACIST,
                                     username="dcstaff")
    malaria = Disease.objects.create(name="Malaria", slug="malaria-dc",
                                     icd10_code="B54", status="published")
    amox = Medication.objects.create(generic_name="Amoxicillin",
                                     status="published")
    patient = Patient.all_objects.create(
        tenant=tenant, first_name="Ada", last_name="Obi", sex="F",
        region="Ikeja, Lagos",
    )
    drug = _stocked(tenant, "Amoxicillin 250mg", medication=amox)
    gloves = _stocked(tenant, "Examination gloves")
    rx = Prescription.all_objects.create(
        tenant=tenant, patient=patient, customer_name="Ada Obi",
        diagnosis="Malaria, uncomplicated", created_by=staff,
    )
    line = PrescriptionItem.all_objects.create(
        tenant=tenant, prescription=rx, item=drug, name=drug.name,
        quantity=10, dosage="500 mg", duration="5 days",
    )
    return {"tenant": tenant, "staff": staff, "patient": patient, "drug": drug,
            "gloves": gloves, "rx": rx, "line": line, "malaria": malaria,
            "amox": amox}


def _sell(counter, item, quantity=10, **kwargs):
    sale = Sale.all_objects.create(tenant=counter["tenant"],
                                   served_by=counter["staff"], **kwargs)
    sale.add_line(item, quantity, user=counter["staff"])
    return sale


def test_dispensing_files_the_diagnosis_and_the_drug(counter):
    """One sale off a script: the case and the drug both reach the centre."""
    _sell(counter, counter["drug"], rx=counter["rx"], patient=counter["patient"])

    case = CaseReport.all_objects.get(tenant=counter["tenant"])
    assert case.disease_id == counter["malaria"].pk      # matched the catalog
    assert case.notes == "Malaria, uncomplicated"        # and kept what was written
    assert case.patient_sex == "F" and case.region == "Ikeja, Lagos"

    order = SurveillanceRx.all_objects.get(tenant=counter["tenant"])
    assert order.medication_id == counter["amox"].pk
    assert order.case_report_id == case.pk                # the drug knows its reason
    assert order.status == SurveillanceRx.Status.DISPENSED
    assert order.dispensed_at is not None
    assert (order.dose, order.duration_days) == ("500 mg", 5)


def test_the_same_row_serves_the_tenant_and_the_centre(counter):
    """No second store: one captured row, read tenant-scoped and pooled."""
    _sell(counter, counter["drug"], rx=counter["rx"], patient=counter["patient"])

    central = prescription_stats(platform=True)
    assert central["dispensed"] == 1
    assert central["top_medications"][0]["medication__generic_name"] == "Amoxicillin"
    assert {row["tenant__name"] for row in central["by_tenant"]} == {"Bola Pharmacy"}

    # Same row, read the way the tenant's own dashboard reads it.
    assert SurveillanceRx.all_objects.filter(
        tenant=counter["tenant"], source_ref=f"rxline:{counter['line'].pk}"
    ).count() == 1


def test_filling_a_script_twice_stays_one_case_and_one_drug(counter):
    """Sold at the till and ticked off at the counter is one dispense, not two."""
    _sell(counter, counter["drug"], rx=counter["rx"], patient=counter["patient"])
    counter["line"].mark_dispensed(user=counter["staff"])
    _sell(counter, counter["drug"], rx=counter["rx"], patient=counter["patient"])

    assert CaseReport.all_objects.filter(tenant=counter["tenant"]).count() == 1
    assert SurveillanceRx.all_objects.filter(tenant=counter["tenant"]).count() == 1


def test_a_hospital_order_is_filled_in_not_filed_again(db_clean):
    """The clinician wrote the order; the hospital's pharmacy only fills it."""
    tenant = Tenant.objects.create(name="St Mary's", slug="st-marys-dc",
                                   kind=Tenant.Kind.HOSPITAL)
    doctor = User.objects.create_user(phone="08030000402", password="x",
                                      tenant=tenant, role=Role.DOCTOR,
                                      username="dcdoctor")
    amox = Medication.objects.create(generic_name="Amoxicillin",
                                     status="published")
    patient = Patient.all_objects.create(tenant=tenant, first_name="Emeka",
                                         last_name="Nwosu", sex="M")
    case = CaseReport.all_objects.create(tenant=tenant, patient=patient,
                                         reporter=doctor)
    order = SurveillanceRx.all_objects.create(
        tenant=tenant, patient=patient, medication=amox, case_report=case,
        reporter=doctor, dose="500 mg",
    )
    item = _stocked(tenant, "Amoxicillin 250mg", medication=amox)

    sale = Sale.all_objects.create(tenant=tenant, patient=patient,
                                   prescription=order)
    sale.add_line(item, 10)

    order.refresh_from_db()
    assert order.status == SurveillanceRx.Status.DISPENSED
    assert order.dispensed_at is not None
    assert SurveillanceRx.all_objects.filter(tenant=tenant).count() == 1


def test_a_walk_in_still_reports_the_drug_but_no_case(counter):
    """Nothing was diagnosed over the counter — the drug used is still reported."""
    _sell(counter, counter["drug"], quantity=5)

    assert CaseReport.all_objects.filter(tenant=counter["tenant"]).count() == 0
    order = SurveillanceRx.all_objects.get(tenant=counter["tenant"])
    assert order.medication_id == counter["amox"].pk
    assert order.case_report_id is None


def test_a_consumable_never_becomes_a_prescribed_drug(counter):
    """Gloves cross the same counter and match no catalog drug."""
    _sell(counter, counter["gloves"], quantity=2)

    assert SurveillanceRx.all_objects.filter(tenant=counter["tenant"]).count() == 0


def test_the_database_refuses_a_second_row_for_one_dispense(counter):
    """What capture keys on, the constraint enforces — a race cannot double it."""
    _sell(counter, counter["drug"], rx=counter["rx"], patient=counter["patient"])
    order = SurveillanceRx.all_objects.get(tenant=counter["tenant"])

    with pytest.raises(IntegrityError), transaction.atomic():
        SurveillanceRx.all_objects.create(
            tenant=counter["tenant"], medication=counter["amox"],
            source_ref=order.source_ref,
        )


def test_hand_filed_rows_do_not_collide(counter):
    """Rows nobody captured carry no source, and no two of them clash."""
    for _ in range(2):
        SurveillanceRx.all_objects.create(tenant=counter["tenant"],
                                          medication=counter["amox"])

    assert SurveillanceRx.all_objects.filter(
        tenant=counter["tenant"], source_ref__isnull=True
    ).count() == 2
