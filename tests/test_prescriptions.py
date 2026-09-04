"""Prescriptions: a doctor writes a drug order against a case, the pharmacy
marks it dispensed, and another tenant never sees it."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport, Prescription
from apps.catalog.models import Disease, Medication
from apps.patients.models import Patient
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c


def test_write_then_dispense(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    doctor = User.objects.create_user(phone="08030000101", password="x",
                                      tenant=a, role=Role.DOCTOR)
    pharmacist = User.objects.create_user(phone="08030000102", password="x",
                                          tenant=a, role=Role.PHARMACIST)
    outsider = User.objects.create_user(phone="08030000103", password="x",
                                        tenant=b, role=Role.PHARMACIST)

    patient = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi")
    disease = Disease.objects.create(name="Malaria", slug="malaria")
    drug = Medication.objects.create(generic_name="Artemether")
    case = CaseReport.all_objects.create(tenant=a, patient=patient, disease=disease)

    written = _client(doctor, a).post("/api/prescriptions/", {
        "patient": patient.id, "case_report": case.id, "medication": drug.id,
        "dose": "500 mg", "frequency": "twice daily", "duration_days": 3,
    }, format="json")
    assert written.status_code == 201, written.content
    rx = Prescription.all_objects.get(pk=written.json()["id"])
    assert rx.reporter_id == doctor.id and rx.tenant_id == a.id
    assert rx.status == Prescription.Status.PRESCRIBED and rx.dispensed_at is None

    dispensed = _client(pharmacist, a).patch(
        f"/api/prescriptions/{rx.pk}/", {"status": "dispensed"}, format="json"
    )
    assert dispensed.status_code == 200, dispensed.content
    rx.refresh_from_db()
    assert rx.status == "dispensed" and rx.dispensed_at is not None

    # Another tenant's pharmacist can't reach the order at all.
    assert _client(outsider, b).get(f"/api/prescriptions/{rx.pk}/").status_code == 404


def test_stats_rollup_and_endpoint(db_clean):
    from apps.analytics.stats import prescription_stats
    from apps.tenants.current import set_current_tenant

    a = Tenant.objects.create(name="A", slug="a")
    set_current_tenant(a)
    drug = Medication.objects.create(generic_name="Artemether")
    other = Medication.objects.create(generic_name="Paracetamol")
    Prescription.objects.create(medication=drug, status="dispensed")
    Prescription.objects.create(medication=drug, status="partially_dispensed")
    Prescription.objects.create(medication=drug, status="prescribed")
    # Cancelled orders are never counted as unfilled.
    Prescription.objects.create(medication=other, status="cancelled")

    stats = prescription_stats()
    assert stats["total"] == 4
    assert stats["dispensed"] == 2
    assert stats["dispense_rate"] == round(2 / 3, 4)
    assert stats["top_medications"][0] == {
        "medication__generic_name": "Artemether", "count": 3
    }

    doctor = User.objects.create_user(phone="08030000104", password="x",
                                      tenant=a, role=Role.DOCTOR)
    r = _client(doctor, a).get("/api/analytics/prescriptions/")
    assert r.status_code == 200, r.content
    assert r.json()["total"] == 4

    # Cross-tenant collation is super-admin only.
    assert _client(doctor, a).get(
        "/api/analytics/platform/prescriptions/"
    ).status_code == 403


def test_pharmacy_tenant_sees_only_patient_linked_orders(db_clean):
    """A pharmacy tenant's list carries only the orders sent for a patient."""
    pharm = Tenant.objects.create(name="Rx", slug="rx-only",
                                  kind=Tenant.Kind.PHARMACY)
    hosp = Tenant.objects.create(name="Gen", slug="gen-hosp",
                                 kind=Tenant.Kind.HOSPITAL)
    drug = Medication.objects.create(generic_name="Amoxicillin")

    for tenant in (pharm, hosp):
        patient = Patient.objects.create(tenant=tenant, first_name="Ada",
                                         last_name="Obi")
        Prescription.all_objects.create(tenant=tenant, patient=patient,
                                        medication=drug, dose="500 mg")
        Prescription.all_objects.create(tenant=tenant, medication=drug,
                                        dose="250 mg")  # no patient

    def _slugs(tenant):
        user = User.objects.create_user(
            phone=f"0803000{tenant.id:04d}", password="x", tenant=tenant,
            role=Role.PHARMACIST,
        )
        body = _client(user, tenant).get("/api/prescriptions/").json()
        return [r["dose"] for r in (body["results"] if isinstance(body, dict) else body)]

    assert _slugs(pharm) == ["500 mg"]          # the unassigned order is hidden
    assert sorted(_slugs(hosp)) == ["250 mg", "500 mg"]


@pytest.mark.parametrize("role", [Role.NURSE, Role.MIDWIFE, Role.CHEW])
def test_nursing_cadres_write_orders_too(db_clean, role):
    """Nurses, midwives and CHEWs prescribe: in a task-shifted service they are
    often the only clinician at the facility, so the order is theirs to write."""
    a = Tenant.objects.create(name="A", slug="a")
    user = User.objects.create_user(phone="08030000201", password="x",
                                    tenant=a, role=role,
                                    license_number=f"LIC-{role}")
    drug = Medication.objects.create(generic_name="Artemether")

    written = _client(user, a).post("/api/prescriptions/", {
        "medication": drug.id, "dose": "500 mg", "frequency": "twice daily",
        "duration_days": 3,
    }, format="json")
    assert written.status_code == 201, written.content
    assert Prescription.all_objects.get(pk=written.json()["id"]).reporter_id == user.id


def test_public_role_cannot_write_orders(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    user = User.objects.create_user(phone="08030000202", password="x",
                                    tenant=a, role=Role.PUBLIC)
    drug = Medication.objects.create(generic_name="Artemether")
    r = _client(user, a).post("/api/prescriptions/",
                              {"medication": drug.id}, format="json")
    assert r.status_code == 403, r.content
