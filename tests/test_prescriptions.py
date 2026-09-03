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
