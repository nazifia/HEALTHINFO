"""An independent prescriber writes under a facility they pick in their state.

Private practice has no employer to scope them, so the row carries a state
instead of a tenant. What that state buys them is a list of facilities to write
under — and nothing outside it: a licence registered in one state is not a
licence to write in the next one.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import Prescription
from apps.catalog.models import Medication
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def world(db):
    """Two states, a clinic in each, and a doctor licensed in the first."""
    lagos = Jurisdiction.objects.create(name="Lagos", level=Jurisdiction.Level.STATE)
    kano = Jurisdiction.objects.create(name="Kano", level=Jurisdiction.Level.STATE)
    ikeja = Jurisdiction.objects.create(
        name="Ikeja", level=Jurisdiction.Level.LOCAL, parent=lagos
    )
    here = Tenant.objects.create(name="Ikeja Clinic", slug="ikeja-clinic",
                                 kind=Tenant.Kind.HOSPITAL, jurisdiction=ikeja)
    away = Tenant.objects.create(name="Kano Clinic", slug="kano-clinic",
                                 kind=Tenant.Kind.HOSPITAL, jurisdiction=kano)
    doctor = User.objects.create_user(
        phone="08030000001", password="x", role=Role.DOCTOR,
        license_number="MDCN123", jurisdiction=lagos,
    )
    drug = Medication.objects.create(generic_name="Artemether")
    yield doctor, here, away, drug
    clear_current_tenant()


def _client(user, tenant=None):
    c = APIClient()
    c.force_authenticate(user=user)
    if tenant is not None:
        c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c


def _order(client, drug):
    return client.post("/api/prescriptions/",
                       {"medication": drug.id, "dose": "80 mg"}, format="json")


def test_no_tenant_and_a_licence_is_an_independent_prescriber(world):
    doctor, _here, _away, _drug = world
    assert doctor.is_independent is True


def test_picker_lists_only_facilities_in_their_state(world):
    doctor, here, away, _drug = world
    rows = _client(doctor).get("/api/tenants/prescribing/").json()
    assert [r["slug"] for r in rows] == [here.slug]
    assert away.slug not in [r["slug"] for r in rows]


def test_writes_under_a_facility_in_their_state(world):
    doctor, here, _away, drug = world
    response = _order(_client(doctor, here), drug)
    assert response.status_code == 201, response.content
    row = Prescription.all_objects.get(pk=response.json()["id"])
    # The order belongs to the facility they picked, and names them as writer.
    assert (row.tenant_id, row.reporter_id) == (here.id, doctor.id)


def test_refused_under_a_facility_in_another_state(world):
    doctor, _here, away, drug = world
    assert _order(_client(doctor, away), drug).status_code == 403


def test_refused_with_no_state_on_the_licence(world):
    doctor, here, _away, drug = world
    User.objects.filter(pk=doctor.pk).update(jurisdiction=None)
    doctor.refresh_from_db()
    assert _order(_client(doctor, here), drug).status_code == 403
    assert _client(doctor).get("/api/tenants/prescribing/").json() == []


def test_the_facility_staff_directory_stays_shut(world):
    doctor, here, _away, _drug = world
    # Prescribing is what the state buys them, not the run of the facility.
    assert _client(doctor, here).get("/api/users/").status_code == 403
    assert _client(doctor, here).get("/api/users/me/").status_code == 200


def test_sees_only_the_patients_they_registered_or_wrote_for(world):
    """A visitor to the facility, not its staff: the registry's unclaimed rows
    and other people's orders stay out of view."""
    from apps.patients.models import Patient
    doctor, here, _away, drug = world
    other = Patient.objects.create(tenant=here, first_name="Ada", last_name="Obi")
    theirs = Patient.objects.create(tenant=here, first_name="Bola",
                                    last_name="Obi", registered_by=doctor)
    Prescription.objects.create(tenant=here, patient=other, medication=drug)
    c = _client(doctor, here)
    # No roster without a search: the register opens one patient at a time.
    assert c.get("/api/patients/").json()["results"] == []
    ids = [r["id"] for r in c.get("/api/patients/?search=Obi").json()["results"]]
    assert ids == [theirs.pk]
    assert c.get(f"/api/patients/{other.pk}/").status_code == 404
    assert c.get("/api/prescriptions/").json()["count"] == 0
    # A patient they cannot open is not one they can write for either: the
    # write would otherwise put them on the caseload by a guessed id.
    refused = c.post("/api/prescriptions/", {"medication": drug.id, "dose": "80 mg",
                                             "patient": other.pk}, format="json")
    assert refused.status_code == 400
    assert c.get(f"/api/patients/{other.pk}/").status_code == 404
    c.post("/api/prescriptions/", {"medication": drug.id, "dose": "80 mg",
                                   "patient": theirs.pk}, format="json")
    # Their orders: nothing unsearched, their own by patient.
    assert c.get("/api/prescriptions/").json()["count"] == 0
    assert c.get("/api/prescriptions/?search=Bola").json()["count"] == 1
    assert c.get(f"/api/prescriptions/?patient={theirs.pk}").json()["count"] == 1
    assert c.get(f"/api/prescriptions/?patient={other.pk}").json()["count"] == 0


def test_clinical_registers_open_to_their_own_work(world):
    """Consultations, case reports, labs and the rest open to them, narrowed
    to what they filed, and the catalog reads but does not write."""
    from apps.analytics.models import CaseReport, Consultation
    from apps.catalog.models import Disease
    from apps.patients.models import Patient
    doctor, here, _away, _drug = world
    theirs = Patient.objects.create(tenant=here, first_name="Bola",
                                    last_name="Obi", registered_by=doctor)
    CaseReport.objects.create(tenant=here, patient=theirs)  # a staff doctor's
    c = _client(doctor, here)
    for path in ("consultations", "case-reports", "adverse-reactions",
                 "lab-results", "immunizations", "vital-events", "appointments"):
        response = c.get(f"/api/{path}/")
        assert response.status_code == 200, path
        assert response.json()["count"] == 0, path
    made = c.post("/api/consultations/", {"patient": theirs.pk,
                                          "chief_complaint": "fever"}, format="json")
    assert made.status_code == 201, made.content
    assert Consultation.all_objects.get(pk=made.json()["id"]).reporter_id == doctor.id
    assert c.get("/api/diseases/").status_code == 200
    assert c.post("/api/diseases/", {"name": "X"}, format="json").status_code == 403
    assert not Disease.all_objects.filter(name="X").exists()


def test_cannot_link_another_clinicians_records(world):
    from apps.analytics.models import CaseReport
    from apps.patients.models import Patient
    doctor, here, _away, drug = world
    other = Patient.objects.create(tenant=here, first_name="Ada", last_name="Obi")
    theirs = Patient.objects.create(tenant=here, first_name="Bola",
                                    last_name="Obi", registered_by=doctor)
    staff_case = CaseReport.objects.create(tenant=here, patient=theirs)
    c = _client(doctor, here)
    unreachable = c.post("/api/consultations/", {"patient": other.pk,
                                                 "chief_complaint": "fever"},
                         format="json")
    assert unreachable.status_code == 400
    assert "caseload" in str(unreachable.content)
    linked = c.post("/api/consultations/", {"patient": theirs.pk,
                                            "chief_complaint": "fever",
                                            "case_report": staff_case.pk},
                    format="json")
    assert linked.status_code == 400
    assert "case_report" in str(linked.content)
    order = c.post("/api/prescriptions/", {"medication": drug.id, "dose": "1",
                                           "patient": theirs.pk,
                                           "case_report": staff_case.pk},
                   format="json")
    assert order.status_code == 400
    assert "case_report" in str(order.content)


def test_a_drug_the_catalog_lacks_is_written_in_words(world):
    doctor, here, _away, _drug = world
    c = _client(doctor, here)
    ok = c.post("/api/prescriptions/", {"medication_text": "Ringer"}, format="json")
    assert ok.status_code == 201 and ok.json()["medication_name"] == "Ringer"
    assert c.post("/api/prescriptions/", {"dose": "1 g"}, format="json").status_code == 400
