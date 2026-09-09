"""Patient portal: a login reaches its own details and the drugs it has
actually been given — nothing else — and the nearby-pharmacy list orders sites
by how far away they actually are."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import Prescription
from apps.branches.models import Branch
from apps.catalog.models import Medication
from apps.patients.models import Patient, PatientAccessLog
from apps.patients.portal import haversine_km
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def _portal(user):
    """A portal client: no tenant header, the way a patient app calls."""
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def linked(db_clean):
    tenant = Tenant.objects.create(name="Clinic", slug="clinic")
    user = User.objects.create_user("08031234567", "pw", tenant=tenant,
                                    role=Role.PUBLIC)
    patient = Patient.objects.create(tenant=tenant, first_name="Ada",
                                     last_name="Obi", user=user)
    return tenant, user, patient


def test_me_returns_only_the_linked_record(linked):
    tenant, user, patient = linked
    Patient.objects.create(tenant=tenant, first_name="Bola", last_name="Eze")

    r = _portal(user).get("/api/portal/me/")

    assert r.status_code == 200
    assert r.data["id"] == patient.id
    assert r.data["full_name"] == "Ada Obi"
    # The read is on the trail like any other read of identifying data.
    assert PatientAccessLog.all_objects.filter(
        patient=patient, user=user, action=PatientAccessLog.Action.RETRIEVE
    ).exists()


def test_account_with_no_patient_record_is_refused(db_clean):
    tenant = Tenant.objects.create(name="Clinic", slug="clinic")
    stranger = User.objects.create_user("08039999999", "pw", tenant=tenant,
                                        role=Role.PUBLIC)

    for path in ("me", "medications"):
        assert _portal(stranger).get(f"/api/portal/{path}/").status_code == 403


def test_medications_lists_only_what_was_dispensed(linked):
    """Their own drugs, and only the ones the counter actually handed over."""
    tenant, user, patient = linked
    drug = Medication.objects.create(tenant=tenant, generic_name="Amoxicillin")
    part = Medication.objects.create(tenant=tenant, generic_name="Metformin")
    waiting = Medication.objects.create(tenant=tenant, generic_name="Ibuprofen")
    other = Patient.objects.create(tenant=tenant, first_name="Bola",
                                   last_name="Eze")
    Prescription.objects.create(tenant=tenant, patient=patient, medication=drug,
                                dose="500 mg",
                                status=Prescription.Status.DISPENSED)
    # Part of it is in their hands, so it counts.
    Prescription.objects.create(tenant=tenant, patient=patient, medication=part,
                                status=Prescription.Status.PARTIAL)
    # Written but not filled, and cancelled at the counter: neither is a drug
    # the patient has.
    Prescription.objects.create(tenant=tenant, patient=patient,
                                medication=waiting,
                                status=Prescription.Status.PRESCRIBED)
    Prescription.objects.create(tenant=tenant, patient=patient, medication=drug,
                                status=Prescription.Status.CANCELLED)
    # Somebody else's dispensed drug stays theirs.
    Prescription.objects.create(tenant=tenant, patient=other, medication=drug,
                                status=Prescription.Status.DISPENSED)

    r = _portal(user).get("/api/portal/medications/")

    assert r.status_code == 200
    assert sorted(row["medication_name"] for row in r.data) == [
        "Amoxicillin", "Metformin",
    ]
    assert [row for row in r.data if row["dose"] == "500 mg"]


def test_a_pending_script_cannot_be_asked_for(linked):
    """?status= is not a way back to what has not been dispensed yet."""
    tenant, user, patient = linked
    drug = Medication.objects.create(tenant=tenant, generic_name="Ibuprofen")
    Prescription.objects.create(tenant=tenant, patient=patient, medication=drug,
                                status=Prescription.Status.PRESCRIBED)

    r = _portal(user).get("/api/portal/medications/?status=prescribed")

    assert r.status_code == 200
    assert r.data == []


def test_the_clinical_timeline_is_not_served_to_patients(linked):
    _tenant, user, _patient = linked
    assert _portal(user).get("/api/portal/history/").status_code == 404


def test_pharmacies_are_ordered_by_distance(linked):
    tenant, user, _patient = linked
    # The tenant's own main branch is created by signal with no coordinates.
    far = Tenant.objects.create(name="Far Pharmacy", slug="far")
    near = Tenant.objects.create(name="Near Pharmacy", slug="near")
    Branch.all_objects.filter(tenant=far).update(latitude=9.05, longitude=7.49)
    Branch.all_objects.filter(tenant=near).update(latitude=6.46, longitude=3.40)

    # Caller in Lagos: the Lagos shop beats the Abuja one, and the branch
    # nobody geocoded comes last rather than being dropped.
    r = _portal(user).get("/api/portal/pharmacies/?lat=6.45&lng=3.39")

    assert r.status_code == 200
    assert [row["pharmacy"] for row in r.data] == [
        "Near Pharmacy", "Far Pharmacy", "Clinic",
    ]
    assert r.data[0]["distance_km"] < r.data[1]["distance_km"]
    assert r.data[2]["distance_km"] is None


def test_pharmacies_without_a_position_still_answer(linked):
    _tenant, user, _patient = linked
    assert _portal(user).get("/api/portal/pharmacies/").status_code == 200
    assert _portal(user).get(
        "/api/portal/pharmacies/?lat=abc&lng=3.39"
    ).status_code == 400


def test_haversine_matches_a_known_distance():
    # Lagos to Abuja is about 525 km great-circle.
    assert 515 < haversine_km(6.46, 3.40, 9.05, 7.49) < 535
