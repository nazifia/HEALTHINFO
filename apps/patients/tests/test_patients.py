"""Patient registry: tenant isolation, the clinical-staff gate, age banding and
the demographics auto-fill that links a patient into the analytics rollups."""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.patients.models import Patient, PatientAccessLog, age_band
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


@pytest.mark.parametrize(
    "years,band",
    [(None, ""), (0, "0-1"), (1, "0-5"), (5, "0-5"), (6, "6-12"), (12, "6-12"),
     (13, "13-18"), (18, "13-18"), (19, "19-40"), (40, "19-40"), (41, "41-60"),
     (60, "41-60"), (61, "60+")],
)
def test_age_band(years, band):
    assert age_band(years) == band


def test_age_and_group_from_dob(db_clean):
    from django.utils import timezone

    t = Tenant.objects.create(name="Clinic", slug="clinic")
    today = timezone.localdate()
    # Born 30 years ago tomorrow → still 29 today (birthday hasn't landed).
    dob = today.replace(year=today.year - 30) + datetime.timedelta(days=1)
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               date_of_birth=dob)
    assert p.age == 29
    assert p.age_group == "19-40"


@pytest.mark.parametrize(
    "patient_type,prefix",
    [("regular", "0"), ("nhia", "4"), ("retainership", "3"), ("staff", "0")],
)
def test_hospital_number_encodes_patient_type(db_clean, patient_type, prefix):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               patient_type=patient_type)
    assert p.hospital_number.startswith(prefix)
    assert len(p.hospital_number) == 10 and p.hospital_number.isdigit()
    assert p.is_nhia is (patient_type == "nhia")


def test_supplied_hospital_number_is_kept(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               patient_type="nhia", hospital_number="MRN-9")
    assert p.hospital_number == "MRN-9"


def test_patients_filter_by_type(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="A",
                           patient_type="nhia")
    Patient.objects.create(tenant=a, first_name="Bola", last_name="B")
    doctor = User.objects.create_user(phone="08030000011", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).get("/api/patients/", {"patient_type": "nhia"})
    assert r.status_code == 200
    rows = r.json()["results"]
    assert [row["first_name"] for row in rows] == ["Ada"]
    assert rows[0]["patient_type_display"] == "NHIA" and rows[0]["is_nhia"] is True


def test_case_report_inherits_patient_demographics(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               sex="F", date_of_birth=datetime.date(1990, 1, 1))
    cr = CaseReport.objects.create(tenant=t, patient=p)
    assert (cr.patient_age_group, cr.patient_sex) == (p.age_group, "F")

    # An explicit value the reporter typed is never overwritten by the link.
    cr2 = CaseReport.objects.create(tenant=t, patient=p, patient_age_group="0-5",
                                    patient_sex="M")
    assert (cr2.patient_age_group, cr2.patient_sex) == ("0-5", "M")


def test_patient_list_is_tenant_scoped(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    Patient.objects.create(tenant=b, first_name="Bola", last_name="B")
    doctor = User.objects.create_user(phone="08030000001", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).get("/api/patients/")
    assert r.status_code == 200
    names = [row["first_name"] for row in r.json()["results"]]
    assert names == ["Ada"]


def test_public_role_cannot_read_patients(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    member = User.objects.create_user(phone="08030000002", password="x",
                                      tenant=a, role=Role.PUBLIC)

    assert _client(member, a).get("/api/patients/").status_code == 403


def test_create_stamps_consent_and_reporter(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    nurse = User.objects.create_user(phone="08030000003", password="x",
                                     tenant=a, role=Role.NURSE)
    r = _client(nurse, a).post("/api/patients/", {
        "first_name": "Ada", "last_name": "Obi", "sex": "F",
        "consent_given": True,
    }, format="json")
    assert r.status_code == 201, r.content
    p = Patient.all_objects.get(pk=r.json()["id"])
    assert p.tenant_id == a.id and p.registered_by_id == nurse.id
    assert p.consent_at is not None


def test_duplicate_hospital_number_rejected(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="A",
                           hospital_number="MRN-1")
    doctor = User.objects.create_user(phone="08030000004", password="x",
                                      tenant=a, role=Role.DOCTOR)
    r = _client(doctor, a).post("/api/patients/", {
        "first_name": "Bola", "last_name": "B", "hospital_number": "MRN-1",
    }, format="json")
    assert r.status_code == 400


def test_nhia_patient_requires_nhis_number(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    doctor = User.objects.create_user(phone="08030000012", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    body = {"first_name": "Ada", "last_name": "Obi", "patient_type": "nhia"}

    r = c.post("/api/patients/", body, format="json")
    assert r.status_code == 400 and "nhis_number" in r.json()["errors"]

    # Blank/whitespace doesn't count as supplying one.
    r = c.post("/api/patients/", {**body, "nhis_number": "  "}, format="json")
    assert r.status_code == 400

    r = c.post("/api/patients/", {**body, "nhis_number": "NHIS-1"}, format="json")
    assert r.status_code == 201, r.content

    # Non-NHIA types are unaffected.
    r = c.post("/api/patients/", {**body, "patient_type": "staff"}, format="json")
    assert r.status_code == 201, r.content


def test_switching_a_patient_to_nhia_needs_the_number(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    doctor = User.objects.create_user(phone="08030000013", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)

    r = c.patch(f"/api/patients/{p.pk}/", {"patient_type": "nhia"}, format="json")
    assert r.status_code == 400 and "nhis_number" in r.json()["errors"]

    r = c.patch(f"/api/patients/{p.pk}/",
                {"patient_type": "nhia", "nhis_number": "NHIS-2"}, format="json")
    assert r.status_code == 200, r.content

    # Already NHIA on file: clearing the number is rejected too.
    r = c.patch(f"/api/patients/{p.pk}/", {"nhis_number": ""}, format="json")
    assert r.status_code == 400


def test_history_returns_linked_records(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    CaseReport.objects.create(tenant=a, patient=p)
    CaseReport.objects.create(tenant=a)  # unlinked — must not show up
    doctor = User.objects.create_user(phone="08030000005", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).get(f"/api/patients/{p.pk}/history/")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["case_reports"] == 1
    assert body["counts"]["appointments"] == 0


def test_reads_are_logged(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    doctor = User.objects.create_user(phone="08030000006", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    c.get("/api/patients/", {"search": "Ada"})
    c.get(f"/api/patients/{p.pk}/")
    c.get(f"/api/patients/{p.pk}/history/")

    rows = PatientAccessLog.all_objects.order_by("id")
    assert [r.action for r in rows] == ["list", "retrieve", "history"]
    assert [r.user_id for r in rows] == [doctor.id] * 3
    assert rows[0].query == "Ada" and rows[0].result_count == 1
    assert rows[1].patient_id == p.pk


def test_access_log_is_admin_only(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    doctor = User.objects.create_user(phone="08030000007", password="x",
                                      tenant=a, role=Role.DOCTOR)
    admin = User.objects.create_user(phone="08030000008", password="x",
                                     tenant=a, role=Role.TENANT_ADMIN)
    _client(doctor, a).get(f"/api/patients/{p.pk}/")

    # The doctor who generated the trail can't audit it.
    assert _client(doctor, a).get("/api/patients/access-log/").status_code == 403

    r = _client(admin, a).get("/api/patients/access-log/", {"patient": p.pk})
    assert r.status_code == 200
    rows = r.json()["results"]
    assert len(rows) == 1
    assert rows[0]["action"] == "retrieve"
    assert rows[0]["user_phone"] == doctor.phone

    # ?action= narrows to one kind of read.
    r = _client(admin, a).get("/api/patients/access-log/", {"action": "history"})
    assert r.status_code == 200 and r.json()["results"] == []


def test_access_log_survives_patient_deletion(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    doctor = User.objects.create_user(phone="08030000009", password="x",
                                      tenant=a, role=Role.DOCTOR)
    _client(doctor, a).get(f"/api/patients/{p.pk}/")
    p.delete()

    row = PatientAccessLog.all_objects.get()
    assert row.patient_id is None and row.action == "retrieve"


def test_reports_filter_by_patient(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    CaseReport.objects.create(tenant=a, patient=p, notes="linked")
    CaseReport.objects.create(tenant=a, notes="walk-in")
    doctor = User.objects.create_user(phone="08030000010", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).get("/api/case-reports/", {"patient": p.pk})
    assert r.status_code == 200
    rows = r.json()["results"]
    assert [row["notes"] for row in rows] == ["linked"]
