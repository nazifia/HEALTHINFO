"""Every way a user is minted leaves a seat that can actually sign in."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.admin import UserCreationFormPhone
from apps.accounts.models import Role, User
from apps.pharmacy.models import HMO
from apps.tenants.models import Jurisdiction, Tenant

PW = "Sup3r-Str0ng-Pw!"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="T", slug="t", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )


@pytest.fixture
def admin(tenant):
    c = APIClient()
    c.force_authenticate(User.objects.create_user(
        phone="08030000001", role=Role.TENANT_ADMIN, tenant=tenant, password="x"
    ))
    return c


def login(body, slug=None):
    extra = {"HTTP_X_TENANT_ID": slug} if slug else {}
    return APIClient().post("/api/auth/token/", body, format="json", **extra)


def mint(admin, tenant, **body):
    r = admin.post("/api/users/", {"password": PW, **body},
                   format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 201, r.content
    return r.json()


def test_public_seat_signs_in_by_phone(admin, tenant):
    mint(admin, tenant, phone="+234 803 123 4567", role="public")
    r = login({"phone": "08031234567", "password": PW}, tenant.slug)
    assert r.status_code == 200, r.content
    assert r.json()["tenant"] == tenant.slug and r.json()["role"] == "public"


def test_doctor_signs_in_by_licence_only(admin, tenant):
    mint(admin, tenant, phone="08031234568", role="doctor",
         license_number="mdcn/12 34", accept_terms=True)
    assert login({"license_number": "MDCN-1234", "password": PW}, tenant.slug).status_code == 200
    assert login({"phone": "08031234568", "password": PW}, tenant.slug).status_code == 401


def test_pharmacist_signs_in_by_last_six_digits_only(admin, tenant):
    mint(admin, tenant, phone="08031234569", role="pharmacist")
    assert login({"phone": "234569", "password": PW}, tenant.slug).status_code == 200
    assert login({"phone": "08031234569", "password": PW}, tenant.slug).status_code == 401


def test_insurer_seat_signs_in(admin, tenant):
    hmo = HMO.objects.create(tenant=tenant, name="H")
    mint(admin, tenant, phone="08031234570", role="hmo", hmo=hmo.id)
    assert login({"phone": "08031234570", "password": PW}, tenant.slug).status_code == 200


def test_government_seat_minted_by_super_admin_signs_in(db, tenant):
    state = Jurisdiction.objects.create(name="Kano", level=Jurisdiction.Level.STATE)
    c = APIClient()
    c.force_authenticate(User.objects.create_superuser(phone="08039999999", password="x"))
    r = c.post("/api/users/", {"phone": "08031234571", "password": PW,
                               "role": "government", "jurisdiction": state.id},
               format="json")
    assert r.status_code == 201, r.content
    r = login({"phone": "08031234571", "password": PW})
    assert r.status_code == 200 and r.json()["tenant"] == ""


def test_registered_patient_signs_in(db, tenant):
    r = APIClient().post("/api/auth/register/", {"phone": "+2348031234572", "password": PW},
                         format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 201, r.content
    assert login({"phone": "0803 123 4572", "password": PW}, tenant.slug).status_code == 200


def test_self_registered_patient_is_active_and_reachable_everywhere(db, tenant):
    from apps.patients.models import Patient

    other = Tenant.objects.create(
        name="O", slug="o", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )
    r = APIClient().post("/api/auth/register/", {
        "phone": "08031234576", "password": PW, "first_name": "Ada",
    }, format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 201, r.content
    patient = Patient.all_objects.get(user__phone="08031234576")
    assert patient.status == Patient.Status.ACTIVE
    # Signs in on a facility they did not sign up at.
    assert login({"phone": "08031234576", "password": PW}, other.slug).status_code == 200
    # Found by a prescriber at that other facility, staff or independent,
    # but on no one's roster.
    state = Jurisdiction.objects.create(name="S", level="state")
    other.jurisdiction = state
    other.save()
    staff = User.objects.create_user(
        phone="08030000002", role=Role.DOCTOR, tenant=other, password="x")
    visitor = User.objects.create_user(
        phone="08030000003", role=Role.DOCTOR, password="x",
        license_number="MDCN9", jurisdiction=state)
    for prescriber in (staff, visitor):
        c = APIClient()
        c.force_authenticate(prescriber)
        hdr = {"HTTP_X_TENANT_ID": other.slug}
        found = c.get("/api/patients/?search=08031234576", **hdr).json()["results"]
        assert [p["id"] for p in found] == [patient.id], prescriber
        roster = c.get("/api/patients/", **hdr).json()["results"]
        assert patient.id not in [p["id"] for p in roster]


def test_backfill_gives_old_signups_a_record_and_skips_linked_ones(db, tenant):
    from importlib import import_module

    from django.apps import apps

    from apps.patients.models import Patient

    backfill = import_module(
        "apps.patients.migrations.0010_backfill_self_registered").backfill
    old = User.objects.create_user(phone="08031234577", tenant=tenant, password="x")
    linked = User.objects.create_user(phone="08031234578", tenant=tenant, password="x")
    Patient.all_objects.create(tenant=tenant, first_name="L", user=linked)
    backfill(apps, None)
    assert Patient.all_objects.get(user=old).registered_by == old
    assert Patient.all_objects.filter(user=linked).count() == 1


def test_onboarded_admin_signs_in(db):
    r = APIClient().post("/api/auth/onboarding/", {
        "org_name": "New Org", "org_slug": "new-org",
        "phone": "+2348031234573", "password": PW,
    }, format="json")
    assert r.status_code == 201, r.content
    r = login({"phone": "08031234573", "password": PW}, "new-org")
    assert r.status_code == 200 and r.json()["role"] == "tenant_admin"


def test_django_admin_form_folds_phone_and_refuses_taken_one(db, tenant):
    User.objects.create_user(phone="08031234574", tenant=tenant, password="x")
    f = UserCreationFormPhone({"phone": "+234 803 123 4574", "password1": PW, "password2": PW})
    assert not f.is_valid() and "phone" in f.errors
    f = UserCreationFormPhone({"phone": "+234 803 123 4575", "password1": PW, "password2": PW})
    assert f.is_valid(), f.errors
    assert f.save().phone == "08031234575"
    assert login({"phone": "08031234575", "password": PW}).status_code == 200
