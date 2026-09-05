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


def test_a_counter_script_has_its_own_path(db_clean):
    """A counter script and a drug order are different records, and both are
    reachable: /api/prescriptions/ is the clinician's order, and the pharmacy's
    script lives under /api/prescriptions/scripts/.

    Registered on the bare prefix, the script viewset was shadowed by the
    analytics one — the URLconf includes analytics first — so nothing could
    list or write a script through the API at all.
    """
    from apps.prescriptions.models import Prescription as Script
    from apps.prescriptions.models import PrescriptionItem

    a = Tenant.objects.create(name="A", slug="a")
    pharmacist = User.objects.create_user(phone="08030000301", password="x",
                                          tenant=a, role=Role.PHARMACIST)
    patient = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi")
    client = _client(pharmacist, a)

    written = client.post("/api/prescriptions/scripts/", {
        "customer_name": "Ada Obi", "patient": patient.id,
        "medications": [{"name": "Artemether", "quantity": 6, "dosage": "1 bd"}],
    }, format="json")
    assert written.status_code == 201, written.content
    script = Script.all_objects.get(pk=written.json()["id"])
    # The patient rides along, which is what puts a dispense in their history.
    lines = PrescriptionItem.all_objects.filter(prescription=script)
    assert script.patient_id == patient.id and lines.count() == 1

    # Same id in both tables, two different records: the bare path must still
    # reach the drug order, not the script.
    assert client.get(f"/api/prescriptions/scripts/{script.pk}/").status_code == 200
    assert client.get(f"/api/prescriptions/{script.pk}/").status_code == 404


def test_one_prescription_carries_several_drugs(db_clean):
    """A visit that calls for three drugs is written once, not three times.

    The rows stay one-drug-each — the pharmacy dispenses them one at a time —
    but they are posted as one list, share the visit's diagnosis and are
    written whole or not at all.
    """
    a = Tenant.objects.create(name="A", slug="a")
    doctor = User.objects.create_user(phone="08030000401", password="x",
                                      tenant=a, role=Role.DOCTOR)
    patient = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi")
    disease = Disease.objects.create(name="Malaria", slug="malaria")
    case = CaseReport.all_objects.create(tenant=a, patient=patient, disease=disease)
    artemether = Medication.objects.create(generic_name="Artemether")
    paracetamol = Medication.objects.create(generic_name="Paracetamol")
    client = _client(doctor, a)

    written = client.post("/api/prescriptions/", [
        {"patient": patient.id, "case_report": case.id,
         "medication": artemether.id, "dose": "80 mg", "frequency": "twice daily"},
        {"patient": patient.id, "case_report": case.id,
         "medication": paracetamol.id, "dose": "1 g", "frequency": "as needed"},
    ], format="json")

    assert written.status_code == 201, written.content
    rows = written.json()
    assert [r["medication_name"] for r in rows] == ["Artemether", "Paracetamol"]
    orders = Prescription.all_objects.filter(patient=patient)
    assert orders.count() == 2
    assert {o.case_report_id for o in orders} == {case.id}
    assert {o.reporter_id for o in orders} == {doctor.id}

    # The rows are one prescription: they share a group, so it can be listed,
    # cancelled or reprinted as the unit it was written as.
    groups = {o.group for o in orders}
    assert len(groups) == 1 and None not in groups
    listed = client.get(f"/api/prescriptions/?group={groups.pop()}").json()
    assert len(listed["results"]) == 2

    # A second prescription for the same patient is its own unit.
    again = client.post("/api/prescriptions/", [
        {"patient": patient.id, "medication": artemether.id, "dose": "80 mg"},
    ], format="json").json()
    assert again[0]["group"] != rows[0]["group"]

    # Nothing prescribed is not a prescription.
    assert client.post("/api/prescriptions/", [], format="json").status_code == 400

    # One bad drug in the list writes none of them: half a prescription is
    # worse than none, because nobody can tell which half. The three rows on
    # file are the two above plus the repeat, and stay three.
    broken = client.post("/api/prescriptions/", [
        {"patient": patient.id, "medication": artemether.id, "dose": "80 mg"},
        {"patient": patient.id, "medication": 999999},
    ], format="json")
    assert broken.status_code == 400, broken.content
    assert Prescription.all_objects.filter(patient=patient).count() == 3


def test_cancelling_one_drug_stops_the_prescription_it_is_on(db_clean):
    """The drugs written together are one decision: stopping one stops them
    all. A drug already handed over stays dispensed — the patient has it."""
    a = Tenant.objects.create(name="A", slug="a")
    doctor = User.objects.create_user(phone="08030000501", password="x",
                                      tenant=a, role=Role.DOCTOR)
    patient = Patient.objects.create(tenant=a, first_name="Ada", last_name="Obi")
    artemether = Medication.objects.create(generic_name="Artemether")
    paracetamol = Medication.objects.create(generic_name="Paracetamol")
    zinc = Medication.objects.create(generic_name="Zinc")
    client = _client(doctor, a)

    rows = client.post("/api/prescriptions/", [
        {"patient": patient.id, "medication": artemether.id, "dose": "80 mg"},
        {"patient": patient.id, "medication": paracetamol.id, "dose": "1 g"},
        {"patient": patient.id, "medication": zinc.id, "dose": "20 mg"},
    ], format="json").json()
    dispensed = Prescription.all_objects.get(pk=rows[2]["id"])
    dispensed.status = Prescription.Status.DISPENSED
    dispensed.save()

    stopped = client.post(f"/api/prescriptions/{rows[0]['id']}/cancel/",
                          format="json")
    assert stopped.status_code == 200, stopped.content
    assert stopped.json()["message"] == "2 drug orders cancelled."
    states = {p.medication_id: p.status for p in
              Prescription.all_objects.filter(patient=patient)}
    assert states[artemether.id] == Prescription.Status.CANCELLED
    assert states[paracetamol.id] == Prescription.Status.CANCELLED
    assert states[zinc.id] == Prescription.Status.DISPENSED

    # An order on no prescription — written before groups, or captured off a
    # counter script — cancels on its own.
    loose = Prescription.all_objects.create(tenant=a, patient=patient,
                                            medication=zinc)
    other = Prescription.all_objects.create(tenant=a, patient=patient,
                                            medication=artemether)
    assert client.post(f"/api/prescriptions/{loose.pk}/cancel/",
                       format="json").status_code == 200
    loose.refresh_from_db()
    other.refresh_from_db()
    assert loose.status == Prescription.Status.CANCELLED
    assert other.status == Prescription.Status.PRESCRIBED
