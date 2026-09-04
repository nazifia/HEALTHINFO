"""A consultation opens once per patient, and closing it settles the visit."""
import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

from apps.analytics.models import Appointment, CaseReport, Consultation, VitalEvent
from apps.analytics.stats import consultation_stats
from apps.catalog.models import Disease, Medication
from apps.patients.models import Patient
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


@pytest.fixture
def patient(tenant):
    return Patient.objects.create(first_name="Ada", last_name="Obi")


def test_one_open_consultation_per_patient(patient):
    Consultation.objects.create(patient=patient, chief_complaint="Fever")
    with pytest.raises(ValueError, match="already has an open consultation"):
        Consultation.objects.create(patient=patient, chief_complaint="Fever again")


def test_close_settles_appointment_and_case_outcome(patient):
    appointment = Appointment.objects.create(patient=patient, reason="Fever")
    case = CaseReport.objects.create(patient=patient, severity="mild")
    consultation = Consultation.objects.create(
        patient=patient, chief_complaint="Fever", appointment=appointment,
        case_report=case,
    )

    consultation.close(disposition=Consultation.Disposition.HOME)

    assert consultation.status == Consultation.Status.CLOSED
    assert consultation.closed_at is not None
    appointment.refresh_from_db()
    case.refresh_from_db()
    assert appointment.status == Appointment.Status.COMPLETED
    assert case.outcome == CaseReport.Outcome.RECOVERED
    # The patient is free to be seen again once the note is closed.
    Consultation.objects.create(patient=patient, chief_complaint="Cough")


def test_closed_note_cannot_be_edited(patient):
    consultation = Consultation.objects.create(patient=patient, chief_complaint="Fever")
    consultation.close(disposition=Consultation.Disposition.REFERRED)

    reloaded = Consultation.objects.get(pk=consultation.pk)
    reloaded.chief_complaint = "Something else"
    with pytest.raises(ValueError, match="cannot be edited"):
        reloaded.save()
    with pytest.raises(ValueError, match="already closed"):
        reloaded.close(disposition=Consultation.Disposition.HOME)


def test_follow_up_disposition_needs_a_date(patient):
    consultation = Consultation.objects.create(patient=patient, chief_complaint="Fever")
    with pytest.raises(ValueError, match="follow-up date"):
        consultation.close(disposition=Consultation.Disposition.FOLLOW_UP)
    consultation.close(
        disposition=Consultation.Disposition.FOLLOW_UP,
        follow_up_on=datetime.date(2026, 10, 1),
    )
    assert consultation.follow_up_on == datetime.date(2026, 10, 1)


def test_close_leaves_an_outcome_someone_already_recorded(patient):
    case = CaseReport.objects.create(patient=patient, outcome=CaseReport.Outcome.REFERRED)
    consultation = Consultation.objects.create(
        patient=patient, chief_complaint="Fever", case_report=case,
    )
    consultation.close(disposition=Consultation.Disposition.HOME)
    case.refresh_from_db()
    assert case.outcome == CaseReport.Outcome.REFERRED


def test_vitals_readouts(patient):
    consultation = Consultation.objects.create(
        patient=patient, chief_complaint="Fever", temperature_c="39.2",
        pulse_bpm=88, systolic_bp=120, diastolic_bp=80,
        weight_kg="70.0", height_cm="170.0",
    )
    assert consultation.bmi == 24.2
    assert consultation.blood_pressure == "120/80"
    # Only the fever is out of band; the unrecorded vitals are not flagged.
    assert consultation.abnormal_vitals == ["temperature_c"]


def test_paediatric_pulse_is_judged_against_a_child_band(tenant):
    baby = Patient.objects.create(
        first_name="Chi", last_name="Obi",
        date_of_birth=datetime.date.today() - datetime.timedelta(days=90),
    )
    consultation = Consultation.objects.create(
        patient=baby, chief_complaint="Cough", pulse_bpm=130, respiratory_rate=40,
    )
    # 130bpm is a flag on the adult band and normal for an infant.
    assert consultation.patient_age_group == "0-1"
    assert consultation.abnormal_vitals == []


def test_deceased_disposition_files_the_death(patient):
    case = CaseReport.objects.create(patient=patient, severity="severe")
    consultation = Consultation.objects.create(
        patient=patient, chief_complaint="Fever", case_report=case, region="Kano",
    )
    consultation.close(disposition=Consultation.Disposition.DECEASED)

    event = VitalEvent.objects.get(patient=patient)
    assert event.event_type == VitalEvent.Kind.DEATH
    assert event.region == "Kano"
    patient.refresh_from_db()
    assert patient.status == Patient.Status.DECEASED
    # A death someone already registered is not counted a second time.
    second = Consultation.objects.create(patient=patient, chief_complaint="—")
    second.close(disposition=Consultation.Disposition.DECEASED)
    assert VitalEvent.objects.filter(patient=patient).count() == 1


def test_consultation_stats_counts_only_closed_dispositions(patient):
    other = Patient.objects.create(first_name="Ba", last_name="Musa")
    Consultation.objects.create(patient=patient, chief_complaint="Fever").close(
        disposition=Consultation.Disposition.ADMITTED
    )
    Consultation.objects.create(patient=other, chief_complaint="Cough")

    stats = consultation_stats()
    assert stats["total"] == 2
    assert stats["open"] == 1
    assert stats["admission_rate"] == 1.0
    assert stats["by_disposition"] == [{"disposition": "admitted", "count": 1}]


def test_child_cuff_band_follows_height(tenant):
    child = Patient.objects.create(
        first_name="Ife", last_name="Obi",
        date_of_birth=datetime.date.today() - datetime.timedelta(days=365 * 3),
    )
    consultation = Consultation.objects.create(
        patient=child, chief_complaint="Cough", height_cm="95.0",
        systolic_bp=85, diastolic_bp=50,
    )
    # 85/50 is low on the adult band and normal for a 95cm child.
    assert consultation.patient_age_group == "0-5"
    assert consultation.abnormal_vitals == []
    # Height is what moves it: an adult's cuff reading on that child is a flag.
    consultation.systolic_bp = 130
    assert consultation.abnormal_vitals == ["systolic_bp"]


def test_stats_report_how_long_a_visit_takes(patient):
    consultation = Consultation.objects.create(patient=patient, chief_complaint="Fever")
    consultation.close(disposition=Consultation.Disposition.HOME)
    Consultation.objects.create(patient=patient, chief_complaint="Cough")  # still open

    minutes = consultation_stats()["median_minutes_to_close"]
    assert 0 <= minutes < 1  # the open note is not counted


def test_median_visit_length_is_the_middle_one(patient):
    opened = timezone.now()
    for pk_minutes in (10, 20, 90):  # median is 20, the mean would be 40
        consultation = Consultation.objects.create(
            patient=patient, chief_complaint="Fever"
        )
        consultation.close(disposition=Consultation.Disposition.HOME)
        Consultation.all_objects.filter(pk=consultation.pk).update(
            created_at=opened,
            closed_at=opened + datetime.timedelta(minutes=pk_minutes),
        )

    assert consultation_stats()["median_minutes_to_close"] == 20.0

    # An even count averages the two either side of the middle: 20 and 90.
    Consultation.all_objects.filter(
        closed_at=opened + datetime.timedelta(minutes=10)
    ).delete()
    assert consultation_stats()["median_minutes_to_close"] == 55.0


def test_guards_hold_with_no_tenant_bound(tenant, patient):
    """A shell session or an import runs outside a request, and the checks that
    keep one open note per patient and one death per patient must still bite."""
    Consultation.objects.create(patient=patient, chief_complaint="Fever")
    dying = Consultation.objects.create(
        patient=Patient.objects.create(first_name="Sa", last_name="Bello"),
        chief_complaint="Sepsis",
    )
    dying.close(disposition=Consultation.Disposition.DECEASED)
    clear_current_tenant()

    with pytest.raises(ValueError, match="already has an open consultation"):
        Consultation(
            tenant=tenant, patient=patient, chief_complaint="Fever again"
        ).save()
    second = Consultation(
        tenant=tenant, patient=dying.patient, chief_complaint="—"
    )
    second.save()
    second.close(disposition=Consultation.Disposition.DECEASED)
    assert VitalEvent.all_objects.filter(patient=dying.patient).count() == 1


def test_refresh_does_not_reopen_a_closed_note(patient):
    consultation = Consultation.objects.create(patient=patient, chief_complaint="Fever")
    # Someone else closed it while this copy was in hand.
    Consultation.objects.get(pk=consultation.pk).close(
        disposition=Consultation.Disposition.HOME
    )
    consultation.refresh_from_db()

    consultation.chief_complaint = "Something else"
    with pytest.raises(ValueError, match="cannot be edited"):
        consultation.save()


@pytest.fixture
def api(tenant, patient):
    """A doctor's client in the patient's hospital."""
    doctor = User.objects.create_user(
        phone="08030000009", password="x", tenant=tenant, role=Role.DOCTOR
    )
    client = APIClient()
    client.force_authenticate(user=doctor)
    client.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return client


def test_api_reports_a_broken_rule_as_a_400(api, patient):
    body = {"patient": patient.id, "chief_complaint": "Fever"}
    assert api.post("/api/consultations/", body, format="json").status_code == 201
    # The second open note for one patient is the client's mistake, not a 500.
    clash = api.post("/api/consultations/", body, format="json")
    assert clash.status_code == 400
    assert "already has an open consultation" in clash.json()["message"]


def test_api_will_not_edit_or_delete_a_signed_note(api, patient):
    created = api.post(
        "/api/consultations/",
        {"patient": patient.id, "chief_complaint": "Fever"}, format="json",
    ).json()
    url = f"/api/consultations/{created['id']}/"
    closed = api.post(url + "close/", {"disposition": "home"}, format="json")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    patched = api.patch(url, {"chief_complaint": "Cough"}, format="json")
    assert patched.status_code == 400
    assert "cannot be edited" in patched.json()["message"]
    deleted = api.delete(url)
    assert deleted.status_code == 400
    assert "cannot be deleted" in deleted.json()["message"]


def test_api_names_the_diagnosis_of_the_linked_case(api, patient):
    """The list carries the diagnosis, so a client shows it without a second fetch."""
    disease = Disease.objects.create(name="Malaria")
    case = CaseReport.objects.create(patient=patient, disease=disease)
    created = api.post(
        "/api/consultations/",
        {"patient": patient.id, "chief_complaint": "Fever", "case_report": case.id},
        format="json",
    ).json()
    assert created["case_report_disease"] == "Malaria"

    # An undiagnosed visit carries no diagnosis name at all — not a blank one
    # a client would print as an empty "Dx:".
    api.post(f"/api/consultations/{created['id']}/close/",
             {"disposition": "home"}, format="json")
    undiagnosed = api.post(
        "/api/consultations/",
        {"patient": patient.id, "chief_complaint": "Cough"}, format="json",
    ).json()
    assert "case_report_disease" not in undiagnosed


def test_prescribing_off_a_visit_files_the_order_against_its_case(api, patient):
    """The app's Prescribe link on a consultation writes a drug order that keeps
    the diagnosis the visit reached."""
    disease = Disease.objects.create(name="Malaria")
    case = CaseReport.objects.create(patient=patient, disease=disease)
    drug = Medication.objects.create(generic_name="Artemether")
    consultation = api.post(
        "/api/consultations/",
        {"patient": patient.id, "chief_complaint": "Fever", "case_report": case.id},
        format="json",
    ).json()
    api.post(f"/api/consultations/{consultation['id']}/close/",
             {"disposition": "home"}, format="json")

    written = api.post(
        "/api/prescriptions/",
        {"patient": patient.id, "medication": drug.id, "dose": "80 mg",
         "frequency": "twice daily", "case_report": case.id},
        format="json",
    )
    assert written.status_code == 201
    assert written.json()["case_report"] == case.id
    assert written.json()["medication_name"] == "Artemether"
