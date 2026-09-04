"""A clinician reads their own case load, not the whole facility's.

Tenant isolation (test_tenant_isolation.py) keeps hospitals apart; this keeps a
doctor inside their own patients and their own filed reports, one hospital in.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.patients.models import Patient
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def hospital(db):
    yield Tenant.objects.create(name="Hospital A", slug="hospital-a")
    clear_current_tenant()


def _user(tenant, role, phone):
    return User.objects.create_user(phone=phone, password="x", tenant=tenant,
                                    role=role)


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c


@pytest.fixture
def caseload(hospital):
    """Two doctors and an admin in one hospital, a patient each."""
    doctor = _user(hospital, Role.DOCTOR, "08030000001")
    other = _user(hospital, Role.DOCTOR, "08030000002")
    admin = _user(hospital, Role.TENANT_ADMIN, "08030000003")
    mine = Patient.objects.create(tenant=hospital, first_name="Ada",
                                  last_name="Obi", registered_by=doctor)
    theirs = Patient.objects.create(tenant=hospital, first_name="Bola",
                                    last_name="Eze", registered_by=other)
    return hospital, doctor, other, admin, mine, theirs


def test_clinician_lists_only_own_patients(caseload):
    hospital, doctor, _other, _admin, mine, theirs = caseload
    body = _client(doctor, hospital).get("/api/patients/").json()
    names = {r["first_name"] for r in body["results"]}
    assert names == {"Ada"}
    assert _client(doctor, hospital).get(f"/api/patients/{theirs.id}/").status_code == 404
    assert _client(doctor, hospital).get(f"/api/patients/{mine.id}/").status_code == 200


def test_filing_a_report_puts_the_patient_on_your_list(caseload):
    hospital, doctor, _other, _admin, _mine, theirs = caseload
    CaseReport.objects.create(tenant=hospital, reporter=doctor, patient=theirs)
    body = _client(doctor, hospital).get("/api/patients/").json()
    assert {r["first_name"] for r in body["results"]} == {"Ada", "Bola"}


def test_tenant_admin_still_sees_the_whole_registry(caseload):
    hospital, _doctor, _other, admin, _mine, _theirs = caseload
    body = _client(admin, hospital).get("/api/patients/").json()
    assert {r["first_name"] for r in body["results"]} == {"Ada", "Bola"}


def test_clinician_lists_only_own_reports(caseload):
    hospital, doctor, other, admin, mine, theirs = caseload
    CaseReport.objects.create(tenant=hospital, reporter=doctor, patient=mine)
    CaseReport.objects.create(tenant=hospital, reporter=other, patient=theirs)

    assert _client(doctor, hospital).get("/api/case-reports/").json()["count"] == 1
    # The admin audits both.
    assert _client(admin, hospital).get("/api/case-reports/").json()["count"] == 2
