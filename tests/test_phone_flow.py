"""Consultation -> prescribing -> dispensing, keyed on the number the patient
hands over at every step: registered with one spelling, looked up with another."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import Consultation, Prescription as DrugOrder
from apps.catalog.models import Disease, Medication
from apps.customers.models import Customer
from apps.inventory.models import StockItem, Store, receive_stock
from apps.pos.models import Sale
from apps.prescriptions.models import Prescription as Script
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PHONE = "08031234567"
SPELLINGS = ("+234 803 123 4567", "0803-123-4567", "2348031234567", PHONE)


@pytest.fixture
def world(db):
    hosp = Tenant.objects.create(name="General Hospital", slug="gen",
                                 kind=Tenant.Kind.HOSPITAL)
    pharm = Tenant.objects.create(name="Bola Pharmacy", slug="bola",
                                  kind=Tenant.Kind.PHARMACY)
    doctor = User.objects.create_user(phone="08030000601", password="x",
                                      tenant=hosp, role=Role.DOCTOR,
                                      username="drada", license_number="MDCN9")
    hosp_pharm = User.objects.create_user(phone="08030000602", password="x",
                                          tenant=hosp, role=Role.PHARMACIST)
    pharmacist = User.objects.create_user(phone="08030000603", password="x",
                                          tenant=pharm, role=Role.PHARMACIST)
    drug = Medication.objects.create(generic_name="Amoxicillin")
    Disease.objects.create(name="Malaria")
    items = {}
    for t in (hosp, pharm):
        items[t.id] = StockItem.all_objects.create(
            tenant=t, name="Amoxicillin 250mg", sku="AMOX250", unit="capsule",
            cost_price=Decimal("10.00"), unit_price=Decimal("25.00"),
            store=Store.RETAIL, medication=drug,
        )
        receive_stock(items[t.id], 50, batch_number="AM-1",
                      cost_price=Decimal("10.00"))
    yield dict(hosp=hosp, pharm=pharm, doctor=doctor, hosp_pharm=hosp_pharm,
               pharmacist=pharmacist, drug=drug, items=items)
    clear_current_tenant()


def _client(user, tenant):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c


def _lookup(client, number, **params):
    r = client.get("/api/prescriptions/scripts/by-number/",
                   {"number": number, **params})
    assert r.status_code == 200, r.content
    return r.json()


def _rows(body):
    return body["results"] if isinstance(body, dict) else body


def test_visit_to_counter_on_the_phone_number(world):
    doc = _client(world["doctor"], world["hosp"])
    # 1. Reception registers the patient with the number as it was said.
    reg = doc.post("/api/patients/", {
        "first_name": "Ada", "last_name": "Obi", "phone": "+234 803 123 4567",
    }, format="json")
    assert reg.status_code == 201, reg.content
    patient = reg.json()
    assert patient["phone"] == PHONE
    assert patient["hospital_number"] == PHONE  # the phone is the card number

    # 2. Reception finds them again by any spelling.
    for spelling in SPELLINGS:
        found = _rows(doc.get("/api/patients/", {"search": spelling}).json())
        assert [p["id"] for p in found] == [patient["id"]], spelling

    # 3. Consultation, diagnosis, prescription off the visit.
    visit = doc.post("/api/consultations/", {
        "patient": patient["id"], "chief_complaint": "Fever",
    }, format="json")
    assert visit.status_code == 201, visit.content
    vid = visit.json()["id"]
    assert doc.post(f"/api/consultations/{vid}/diagnose/",
                    {"diagnosis": "Malaria"}, format="json").status_code == 200
    order = doc.post("/api/prescriptions/", {
        "patient": patient["id"], "medication": world["drug"].id,
        "dose": "500 mg", "consultation_category": "A",
    }, format="json")
    assert order.status_code == 201, order.content
    oid = order.json()["id"]
    assert order.json()["case_report"] == \
        Consultation.all_objects.get(pk=vid).case_report_id
    assert doc.post(f"/api/consultations/{vid}/close/",
                    {"disposition": "home"}, format="json").status_code == 200

    # 4. Hospital pharmacy finds the order on any spelling of the number.
    hp = _client(world["hosp_pharm"], world["hosp"])
    for spelling in SPELLINGS:
        body = _lookup(hp, spelling, undispensed=1)
        assert [o["id"] for o in body["orders"]] == [oid], spelling
    # ...and on the hospital number.
    assert [o["id"] for o in
            _lookup(hp, patient["hospital_number"])["orders"]] == [oid]

    # 5. Outside pharmacy: whole number in any spelling, never a fragment.
    out = _client(world["pharmacist"], world["pharm"])
    for spelling in SPELLINGS:
        body = _lookup(out, spelling, undispensed=1)
        assert [o["id"] for o in body["orders_elsewhere"]] == [oid], spelling
        assert body["orders"] == []
    assert _lookup(out, "80312345")["orders_elsewhere"] == []

    # 6. Outside pharmacy dispenses on the number, in any spelling.
    sold = out.post("/api/pos/sales/", {
        "items": [{"item": world["items"][world["pharm"].id].pk, "quantity": 10}],
        "prescription": oid, "patient_number": "+234 (803) 123-4567",
    }, format="json")
    assert sold.status_code == 201, sold.content
    assert DrugOrder.all_objects.get(pk=oid).status == DrugOrder.Status.DISPENSED
    assert _lookup(out, PHONE, undispensed=1)["orders_elsewhere"] == []
    assert _lookup(hp, PHONE, undispensed=1)["orders"] == []


def test_counter_customer_by_phone_spelling(world):
    """A customer keyed at the counter with one spelling is the same person
    when they come back with another."""
    out = _client(world["pharmacist"], world["pharm"])
    made = out.post("/api/customers/", {
        "name": "Ada Obi", "phone": "+234 803 123 4567",
    }, format="json")
    assert made.status_code == 201, made.content
    cid = made.json()["id"]
    assert made.json()["phone"] == PHONE

    # Same number, other spelling: a duplicate, not a second customer.
    again = out.post("/api/customers/", {"name": "Ada", "phone": "0803-123-4567"},
                     format="json")
    assert again.status_code == 400, again.content
    assert Customer.all_objects.filter(tenant=world["pharm"]).count() == 1

    for spelling in SPELLINGS:
        found = _rows(out.get("/api/customers/", {"search": spelling}).json())
        assert [c["id"] for c in found] == [cid], spelling

    # A script written against the customer is found by the number, and the
    # sale off it against that customer ticks it off.
    script = out.post("/api/prescriptions/scripts/", {
        "customer": cid, "customer_name": "Ada Obi",
        "medications": [{"name": "Amoxicillin", "quantity": 10}],
    }, format="json")
    assert script.status_code == 201, script.content
    sid = script.json()["id"]
    for spelling in SPELLINGS:
        assert [s["id"] for s in _lookup(out, spelling)["scripts"]] == [sid], spelling

    sold = out.post("/api/pos/sales/", {
        "items": [{"item": world["items"][world["pharm"].id].pk, "quantity": 10}],
        "rx": sid, "customer": cid,
    }, format="json")
    assert sold.status_code == 201, sold.content
    assert Script.all_objects.get(pk=sid).status == Script.Status.DISPENSED
    assert Sale.all_objects.get(pk=sold.json()["id"]).customer_id == cid

    # A second script against the customer, with no phone typed on it, still
    # reaches another counter on the customer's number and is filled there.
    second = out.post("/api/prescriptions/scripts/", {
        "customer": cid, "medications": [{"name": "Amoxicillin", "quantity": 5}],
    }, format="json").json()
    assert second["customer_phone"] == PHONE
    hp = _client(world["hosp_pharm"], world["hosp"])
    assert [s["id"] for s in
            _lookup(hp, "+234 803 123 4567", undispensed=1)["scripts_elsewhere"]
            ] == [second["id"]]
    filled = hp.post("/api/pos/sales/", {
        "items": [{"item": world["items"][world["hosp"].id].pk, "quantity": 5}],
        "rx": second["id"], "patient_number": "0803-123-4567",
    }, format="json")
    assert filled.status_code == 201, filled.content
    assert Script.all_objects.get(pk=second["id"]).status == Script.Status.DISPENSED


def test_walk_in_script_elsewhere_on_any_spelling(world):
    """A script written up for a walk-in at one pharmacy, filled at another on
    the phone alone: written and read in different spellings."""
    hp = _client(world["hosp_pharm"], world["hosp"])
    script = hp.post("/api/prescriptions/scripts/", {
        "customer_name": "Ada", "customer_phone": "0803 123 4567",
        "medications": [{"name": "Amoxicillin", "quantity": 10}],
    }, format="json")
    assert script.status_code == 201, script.content
    sid = script.json()["id"]
    out = _client(world["pharmacist"], world["pharm"])
    for spelling in SPELLINGS:
        assert [s["id"] for s in
                _lookup(out, spelling)["scripts_elsewhere"]] == [sid], spelling
    sold = out.post("/api/pos/sales/", {
        "items": [{"item": world["items"][world["pharm"].id].pk, "quantity": 10}],
        "rx": sid, "patient_number": "+2348031234567",
    }, format="json")
    assert sold.status_code == 201, sold.content
    assert Script.all_objects.get(pk=sid).status == Script.Status.DISPENSED
