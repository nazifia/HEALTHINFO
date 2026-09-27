"""A doctor, nurse, midwife or pharmacist opens their own independent seat.

The seat carries a state instead of a facility and opens straight away.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction


@pytest.fixture
def lagos(db):
    yield Jurisdiction.objects.create(name="Lagos", level=Jurisdiction.Level.STATE)
    clear_current_tenant()


def _signup(**extra):
    body = {"phone": "08030000009", "password": "s3curepass99", **extra}
    return APIClient().post("/api/auth/register/", body, format="json")


@pytest.mark.parametrize("role", ["doctor", "nurse", "midwife", "pharmacist"])
def test_prescriber_signs_up_independent_and_active(lagos, role):
    r = _signup(role=role, license_number="lic-001", jurisdiction=lagos.id,
                accept_terms=True)
    assert r.status_code == 201, r.content
    user = User.objects.get(phone="08030000009")
    assert (user.role, user.tenant_id, user.jurisdiction_id) == (role, None, lagos.id)
    assert user.is_independent and user.is_active
    assert user.terms_accepted_at is not None


def test_prescriber_needs_licence_state_and_terms(lagos):
    r = _signup(role="doctor")
    assert r.status_code == 400
    assert {"license_number", "jurisdiction", "accept_terms"} <= set(r.json()["errors"])


def test_state_only_not_local_government(lagos):
    ikeja = Jurisdiction.objects.create(
        name="Ikeja", level=Jurisdiction.Level.LOCAL, parent=lagos)
    r = _signup(role="nurse", license_number="N1", jurisdiction=ikeja.id,
                accept_terms=True)
    assert r.status_code == 400 and "jurisdiction" in r.json()["errors"]


def test_other_roles_are_still_not_self_assignable(lagos):
    # No tenant for a patient signup, so the fallback to public is refused.
    r = _signup(role="chew", license_number="C1", jurisdiction=lagos.id,
                accept_terms=True)
    assert r.status_code == 400 and "tenant" in r.json()["errors"]
    assert not User.objects.filter(role=Role.CHEW).exists()


def test_independent_pharmacist_signs_in_by_licence(lagos):
    _signup(role="pharmacist", license_number="PCN-7", jurisdiction=lagos.id,
            accept_terms=True)
    login = {"license_number": "PCN-7", "password": "s3curepass99"}
    r = APIClient().post("/api/auth/token/", login, format="json")
    assert r.status_code == 200, r.content
    # Not the pharmacy short code: they have no pharmacy.
    short = {"phone": "000009", "password": "s3curepass99"}
    assert APIClient().post("/api/auth/token/", short, format="json").status_code == 401


def test_independent_pharmacist_picks_a_facility_and_prescribes(lagos):
    from apps.catalog.models import Medication
    from apps.tenants.models import Tenant

    ikeja = Jurisdiction.objects.create(
        name="Ikeja", level=Jurisdiction.Level.LOCAL, parent=lagos)
    clinic = Tenant.objects.create(name="Ikeja Clinic", slug="ikeja-clinic",
                                   kind=Tenant.Kind.HOSPITAL, jurisdiction=ikeja)
    _signup(role="pharmacist", license_number="PCN-8", jurisdiction=lagos.id,
            accept_terms=True)
    c = APIClient()
    c.force_authenticate(User.objects.get(phone="08030000009"))
    assert [r["slug"] for r in c.get("/api/tenants/prescribing/").json()] == [clinic.slug]
    c.credentials(HTTP_X_TENANT_ID=clinic.slug)
    drug = Medication.objects.create(generic_name="Artemether")
    r = c.post("/api/prescriptions/", {"medication": drug.id, "dose": "80 mg"},
               format="json")
    assert r.status_code == 201, r.content
    assert c.get("/api/patients/").status_code == 200


# ----- staff asking to join an existing organization --------------------------

@pytest.fixture
def clinic(db):
    from apps.tenants.models import Tenant
    yield Tenant.objects.create(name="Clinic", slug="clinic")
    clear_current_tenant()


def _join(tenant, **extra):
    body = {"phone": "08030000019", "password": "s3curepass99",
            "join_as_staff": True, **extra}
    c = APIClient()
    c.credentials(HTTP_X_TENANT_ID=tenant.slug)
    return c.post("/api/auth/register/", body, format="json")


def test_staff_joins_organization_inactive(clinic):
    r = _join(clinic, role="nurse", license_number="N-55", accept_terms=True)
    assert r.status_code == 201, r.content
    user = User.objects.get(phone="08030000019")
    assert (user.role, user.tenant_id, user.is_active) == ("nurse", clinic.id, False)
    assert user.terms_accepted_at is not None
    # No patient record for a staff seat.
    from apps.patients.models import Patient
    assert not Patient.all_objects.filter(user=user).exists()
    # Cannot sign in until the admin approves.
    login = APIClient()
    login.credentials(HTTP_X_TENANT_ID=clinic.slug)
    assert login.post("/api/auth/token/", {"license_number": "N-55",
                      "password": "s3curepass99"}, format="json").status_code == 401


def test_licensed_staff_need_licence_and_terms(clinic):
    r = _join(clinic, role="chew")
    assert r.status_code == 400
    assert {"license_number", "accept_terms"} <= set(r.json()["errors"])


def test_receptionist_joins_without_licence(clinic):
    assert _join(clinic, role="receptionist").status_code == 201


def test_staff_cannot_self_assign_admin(clinic):
    r = _join(clinic, role="tenant_admin")
    assert r.status_code == 400 and "role" in r.json()["errors"]
    assert not User.objects.filter(role=Role.TENANT_ADMIN).exists()


def test_staff_needs_an_organization(db):
    r = _signup(role="doctor", join_as_staff=True, license_number="D1",
                accept_terms=True)
    assert r.status_code == 400 and "tenant" in r.json()["errors"]


def test_admin_is_mailed_and_sees_request_then_staff_signs_in(clinic, mailoutbox, django_capture_on_commit_callbacks):
    admin = User.objects.create_user(phone="08030000020", password="x", tenant=clinic,
                                     role=Role.TENANT_ADMIN, email="boss@clinic.ng")
    with django_capture_on_commit_callbacks(execute=True):
        assert _join(clinic, role="receptionist", username="ada").status_code == 201
    assert mailoutbox and mailoutbox[0].to == ["boss@clinic.ng"]
    assert "ada" in mailoutbox[0].body

    c = APIClient()
    c.force_authenticate(user=admin)
    c.credentials(HTTP_X_TENANT_ID=clinic.slug)
    pending = {"is_active": "false", "last_login__isnull": "true"}
    rows = c.get("/api/users/", pending).json()
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    assert [u["phone"] for u in rows] == ["08030000019"]
    assert c.patch(f"/api/users/{rows[0]['id']}/", {"is_active": True},
                   format="json").status_code == 200

    # Sign-in carries no organization; the token answer names it.
    r = APIClient().post("/api/auth/token/", {"phone": "08030000019",
                         "password": "s3curepass99"}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["tenant"] == "clinic"
    rows = c.get("/api/users/", pending).json()
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    assert rows == []
