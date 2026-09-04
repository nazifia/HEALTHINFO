"""Patient registry: tenant isolation, the clinical-staff gate, age banding and
the demographics auto-fill that links a patient into the analytics rollups."""
import datetime

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport, Prescription
from apps.catalog.models import Disease, Medication
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


def test_phone_becomes_the_hospital_number(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               phone="+234 803 123 4567")
    assert p.hospital_number == "08031234567"


def test_shared_phone_falls_back_to_a_generated_number(db_clean):
    """A family line belongs to whoever was registered on it first."""
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    first = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                                   phone="08031234567")
    second = Patient.objects.create(tenant=t, first_name="Ola", last_name="Obi",
                                    phone="08031234567")
    assert first.hospital_number == "08031234567"
    assert second.hospital_number != first.hospital_number
    assert len(second.hospital_number) == 10


def test_number_follows_a_corrected_phone(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               phone="08031234567")
    p = Patient.all_objects.get(pk=p.pk)
    p.phone = "08039999999"
    p.save(update_fields=["phone"])
    assert Patient.all_objects.get(pk=p.pk).hospital_number == "08039999999"


def test_a_hand_typed_number_ignores_the_phone(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               phone="08031234567", hospital_number="MRN-9")
    p = Patient.all_objects.get(pk=p.pk)
    p.phone = "08039999999"
    p.save()
    assert p.hospital_number == "MRN-9"


def test_number_stays_when_the_new_phone_is_someone_elses(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    Patient.objects.create(tenant=t, first_name="Ola", last_name="Obi",
                           phone="08039999999")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               phone="08031234567")
    p = Patient.all_objects.get(pk=p.pk)
    p.phone = "08039999999"
    p.save()
    assert p.hospital_number == "08031234567"


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


@pytest.mark.parametrize(
    "role", [Role.DOCTOR, Role.PHARMACIST, Role.NURSE, Role.MIDWIFE, Role.CHEW]
)
def test_clinical_cadres_register_edit_and_diagnose(db_clean, role):
    """Every clinical cadre registers a patient, edits it, and files the
    diagnosis + prescribed medication against it."""
    a = Tenant.objects.create(name="A", slug="a")
    staff = User.objects.create_user(phone="08031000001", password="x",
                                     tenant=a, role=role)
    client = _client(staff, a)

    created = client.post("/api/patients/", {
        "first_name": "Ada", "last_name": "Obi", "sex": "F",
        "consent_given": True,
    }, format="json")
    assert created.status_code == 201, created.content
    patient_id = created.json()["id"]

    edited = client.patch(f"/api/patients/{patient_id}/",
                          {"last_name": "Obiora"}, format="json")
    assert edited.status_code == 200, edited.content

    disease = Disease.objects.create(name="Malaria", slug=f"malaria-{role}")
    drug = Medication.objects.create(generic_name="Artemether")
    report = client.post("/api/case-reports/", {
        "patient": patient_id, "disease": disease.id, "medications": [drug.id],
        "severity": "mild",
    }, format="json")
    assert report.status_code == 201, report.content
    filed = CaseReport.all_objects.get(pk=report.json()["id"])
    assert filed.reporter_id == staff.id
    assert filed.disease_id == disease.id
    assert list(filed.medications.values_list("id", flat=True)) == [drug.id]


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


def test_age_stops_at_date_of_death(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    p = Patient.objects.create(tenant=t, first_name="Ada", last_name="Obi",
                               date_of_birth=datetime.date(1950, 6, 1),
                               date_of_death=datetime.date(2000, 5, 31))
    assert p.age == 49  # birthday hadn't landed yet that year
    assert p.age_group == "41-60"
    # The date is the harder fact: it sets the status whatever was sent.
    assert p.status == Patient.Status.DECEASED


def test_death_date_is_validated(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    doctor = User.objects.create_user(phone="08030000012", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    body = {"first_name": "Ada", "last_name": "Obi",
            "date_of_birth": "1990-01-01", "date_of_death": "1989-12-31"}
    r = c.post("/api/patients/", body, format="json")
    assert r.status_code == 400 and "date_of_death" in r.json()["errors"]

    future = datetime.date.today() + datetime.timedelta(days=1)
    body["date_of_death"] = future.isoformat()
    assert c.post("/api/patients/", body, format="json").status_code == 400


def test_duplicate_registration_needs_an_override(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                           date_of_birth=datetime.date(1990, 1, 1),
                           hospital_number="MRN-7")
    doctor = User.objects.create_user(phone="08030000013", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    body = {"first_name": "ada", "last_name": "OBI",  # case doesn't launder it
            "date_of_birth": "1990-01-01"}

    r = c.post("/api/patients/", body, format="json")
    assert r.status_code == 400
    assert "MRN-7" in str(r.json()["errors"]["allow_duplicate"])

    # Same names, different birthday — a different person, goes through.
    r = c.post("/api/patients/", {**body, "date_of_birth": "1991-01-01"},
               format="json")
    assert r.status_code == 201, r.content

    # Real twin/namesake: the registrar overrides and it's accepted.
    r = c.post("/api/patients/", {**body, "allow_duplicate": True}, format="json")
    assert r.status_code == 201, r.content
    assert Patient.all_objects.filter(date_of_birth="1990-01-01").count() == 2


def test_registered_death_marks_the_patient_deceased(db_clean):
    from apps.analytics.models import VitalEvent

    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A",
                               date_of_birth=datetime.date(1990, 1, 1))
    VitalEvent.objects.create(tenant=a, patient=p, event_type="death")
    p.refresh_from_db()
    assert p.status == Patient.Status.DECEASED and p.date_of_death is not None

    # A birth leaves the registry alone.
    q = Patient.objects.create(tenant=a, first_name="Bola", last_name="B")
    VitalEvent.objects.create(tenant=a, patient=q, event_type="birth")
    q.refresh_from_db()
    assert q.status == Patient.Status.ACTIVE and q.date_of_death is None


def test_deletion_is_logged_with_the_identity(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A",
                               hospital_number="MRN-8")
    doctor = User.objects.create_user(phone="08030000014", password="x",
                                      tenant=a, role=Role.DOCTOR)

    assert _client(doctor, a).delete(f"/api/patients/{p.pk}/").status_code == 204
    assert not Patient.all_objects.filter(pk=p.pk).exists()

    row = PatientAccessLog.all_objects.get()
    # The FK is gone with the row, so the log has to carry who it was.
    assert row.action == "delete" and row.patient_id is None
    assert "MRN-8" in row.query and "Ada" in row.query


def test_reports_cannot_link_another_tenants_patient(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    theirs = Patient.objects.create(tenant=b, first_name="Bola", last_name="B")
    doctor = User.objects.create_user(phone="08030000015", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).post("/api/case-reports/", {"patient": theirs.pk},
                                format="json")
    assert r.status_code == 400 and "patient" in r.json()["errors"]


@pytest.mark.parametrize(
    "typed,stored",
    [("+2348031234567", "08031234567"), ("0803 123 4567", "08031234567"),
     ("0803-123-4567", "08031234567"), ("2348031234567", "08031234567"),
     ("08031234567", "08031234567")],
)
def test_phone_is_stored_in_one_shape(db_clean, typed, stored):
    a = Tenant.objects.create(name="A", slug="a")
    doctor = User.objects.create_user(phone="08030000016", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    r = c.post("/api/patients/", {"first_name": "Ada", "last_name": "Obi",
                                  "phone": typed,
                                  "next_of_kin_phone": typed}, format="json")
    assert r.status_code == 201, r.content
    p = Patient.all_objects.get(pk=r.json()["id"])
    assert p.phone == stored and p.next_of_kin_phone == stored
    # And the number is findable however the searcher types it.
    assert c.get("/api/patients/", {"search": "8031234567"}).json()["count"] == 1


def test_patient_with_records_cannot_be_deleted(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    CaseReport.objects.create(tenant=a, patient=p)
    doctor = User.objects.create_user(phone="08030000017", password="x",
                                      tenant=a, role=Role.DOCTOR)

    r = _client(doctor, a).delete(f"/api/patients/{p.pk}/")
    assert r.status_code == 400
    # DRF stringifies the detail; the shape is what matters.
    assert r.json()["errors"]["clinical_records"] == {"casereports": "1"}
    assert Patient.all_objects.filter(pk=p.pk).exists()
    # Nothing was deleted, so nothing is logged as deleted either.
    assert not PatientAccessLog.all_objects.filter(action="delete").exists()


def test_merge_moves_records_and_leaves_a_tombstone(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    keep = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                                  hospital_number="MRN-A")
    dupe = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                                  hospital_number="MRN-B", phone="08031234567",
                                  date_of_birth=datetime.date(1990, 1, 1))
    CaseReport.objects.create(tenant=a, patient=dupe, notes="on the duplicate")
    admin = User.objects.create_user(phone="08030000018", password="x",
                                     tenant=a, role=Role.TENANT_ADMIN)

    r = _client(admin, a).post(f"/api/patients/{keep.pk}/merge/",
                               {"source": dupe.pk}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["moved"] == {"casereports": 1}

    keep.refresh_from_db()
    dupe.refresh_from_db()
    # Records follow the survivor; blanks on it are filled from the duplicate.
    assert CaseReport.all_objects.get().patient_id == keep.pk
    assert keep.phone == "08031234567"
    assert keep.date_of_birth == datetime.date(1990, 1, 1)
    assert keep.hospital_number == "MRN-A"  # its own identity is never taken
    # The duplicate stays reachable and points at the survivor.
    assert dupe.status == "merged" and dupe.merged_into_id == keep.pk
    assert _client(admin, a).get(f"/api/patients/{dupe.pk}/").status_code == 200

    # ...but is out of the way of everyday lists unless asked for by status.
    rows = _client(admin, a).get("/api/patients/").json()["results"]
    assert [row["hospital_number"] for row in rows] == ["MRN-A"]
    rows = _client(admin, a).get("/api/patients/", {"status": "merged"}).json()
    assert [row["hospital_number"] for row in rows["results"]] == ["MRN-B"]

    row = PatientAccessLog.all_objects.filter(action="merge").get()
    assert "MRN-B" in row.query and "MRN-A" in row.query


def test_merge_is_admin_only_and_rejects_nonsense(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    b = Tenant.objects.create(name="B", slug="b")
    keep = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    theirs = Patient.objects.create(tenant=b, first_name="Bola", last_name="B")
    doctor = User.objects.create_user(phone="08030000019", password="x",
                                      tenant=a, role=Role.DOCTOR)
    admin = User.objects.create_user(phone="08030000020", password="x",
                                     tenant=a, role=Role.TENANT_ADMIN)

    url = f"/api/patients/{keep.pk}/merge/"
    assert _client(doctor, a).post(url, {"source": keep.pk},
                                   format="json").status_code == 403
    c = _client(admin, a)
    assert c.post(url, {"source": keep.pk}, format="json").status_code == 400
    # Another tenant's patient isn't even visible, let alone mergeable.
    assert c.post(url, {"source": theirs.pk}, format="json").status_code == 400
    assert c.post(url, {}, format="json").status_code == 400


def test_merged_status_cannot_be_set_by_hand(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="A")
    doctor = User.objects.create_user(phone="08030000021", password="x",
                                      tenant=a, role=Role.DOCTOR)

    # Otherwise anyone could hide a record from every list by relabelling it.
    r = _client(doctor, a).patch(f"/api/patients/{p.pk}/", {"status": "merged"},
                                 format="json")
    assert r.status_code == 400 and "status" in r.json()["errors"]


@pytest.mark.parametrize(
    "typed",
    ["+2348031234567", "2348031234567", "0803-123-4567", "0803 123 4567",
     "(0803) 123 4567", "08031234567", "8031234567"],
)
def test_phone_is_findable_however_it_is_typed(db_clean, typed):
    """Numbers are stored in one shape; the search box has to speak all of them."""
    a = Tenant.objects.create(name="A", slug="a")
    Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                           phone="08031234567")
    doctor = User.objects.create_user(phone="08030000030", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    assert c.get("/api/patients/", {"search": typed}).json()["count"] == 1


def test_hospital_number_search_survives_the_phone_folding(db_clean):
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                               hospital_number="0123456789")
    doctor = User.objects.create_user(phone="08030000031", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    body = c.get("/api/patients/", {"search": "0123456789"}).json()
    assert body["count"] == 1 and body["results"][0]["id"] == p.pk


def test_next_of_kin_phone_finds_the_patient(db_clean):
    """Reception is often given the relative's number, not the patient's."""
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                               phone="08031234567",
                               next_of_kin_phone="08039999999")
    doctor = User.objects.create_user(phone="08030000032", password="x",
                                      tenant=a, role=Role.DOCTOR)
    c = _client(doctor, a)
    body = c.get("/api/patients/", {"search": "+2348039999999"}).json()
    assert body["count"] == 1 and body["results"][0]["id"] == p.pk


def test_an_nhis_number_starting_234_is_not_read_as_a_country_code(db_clean):
    """Only a Nigerian mobile is folded; every other number keeps its digits."""
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi",
                               nhis_number="2345678901")
    doctor = User.objects.create_user(phone="08030000033", password="x",
                                      tenant=a, role=Role.DOCTOR)
    body = _client(doctor, a).get("/api/patients/",
                                  {"search": "2345678901"}).json()
    assert body["count"] == 1 and body["results"][0]["id"] == p.pk


def test_the_prescriber_can_find_the_patient_they_prescribed_for(db_clean):
    """A doctor's caseload includes the patients they wrote an order for —
    otherwise the search that follows up a prescription finds nothing."""
    a = Tenant.objects.create(name="A", slug="a")
    p = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi")
    mine = User.objects.create_user(phone="08030000034", password="x",
                                    tenant=a, role=Role.DOCTOR)
    other = User.objects.create_user(phone="08030000035", password="x",
                                     tenant=a, role=Role.DOCTOR)
    # registered_by set, so the patient is not visible to everyone by default.
    p.registered_by = other
    p.save(update_fields=["registered_by"])
    drug = Medication.objects.create(generic_name="Artemether")
    Prescription.objects.create(tenant=a, patient=p, medication=drug,
                                reporter=mine)

    body = _client(mine, a).get("/api/patients/", {"search": "Obi"}).json()
    assert [row["id"] for row in body["results"]] == [p.pk]


def test_a_lookup_can_ask_for_a_short_page(db_clean):
    """The typeahead lookups ask for the first few matches, not a full page."""
    a = Tenant.objects.create(name="A", slug="a")
    for i in range(7):
        Patient.objects.create(tenant=a, first_name=f"Ada{i}", last_name="Obi")
    doctor = User.objects.create_user(phone="08030000036", password="x",
                                      tenant=a, role=Role.DOCTOR)
    body = _client(doctor, a).get("/api/patients/",
                                  {"search": "Obi", "page_size": 5}).json()
    assert body["count"] == 7 and len(body["results"]) == 5
