"""A principal names a dependent from the portal; the scheme's seat answers,
and can change that answer later."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.patients.models import Patient
from apps.pharmacy.models import HMO, HmoEnrollment, SchemeDependent
from apps.pos.models import Notification
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def world(db):
    pharm = Tenant.objects.create(name="Pharm", slug="pharm")
    clinic = Tenant.objects.create(name="Clinic", slug="clinic")
    hmo = HMO.objects.create(tenant=pharm, name="Hygeia")
    rival = HMO.objects.create(tenant=pharm, name="Reliance")
    principal = User.objects.create_user("08031234567", "pw", tenant=clinic,
                                         role=Role.PUBLIC)
    patient = Patient.objects.create(tenant=clinic, first_name="Ada",
                                     last_name="Obi", user=principal)
    card = HmoEnrollment.objects.create(tenant=pharm, patient=patient, hmo=hmo,
                                        member_number="HYG-1")
    seat = User.objects.create_user("08030000001", "pw", tenant=pharm,
                                    role=Role.HMO, hmo=hmo, is_admin=True)
    rival_seat = User.objects.create_user("08030000002", "pw", tenant=pharm,
                                          role=Role.HMO, hmo=rival, is_admin=True)
    yield dict(pharm=pharm, hmo=hmo, principal=principal, patient=patient,
               card=card, seat=seat, rival_seat=rival_seat)
    clear_current_tenant()


def portal(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def desk(user):
    c = portal(user)
    c.defaults["HTTP_X_TENANT_ID"] = "pharm"
    return c


def test_principal_adds_and_scheme_approves_then_changes_its_mind(world):
    r = portal(world["principal"]).post("/api/portal/dependents/", {
        "full_name": "Tobi Obi", "relationship": "child", "sex": "M",
        "date_of_birth": "2019-05-01",
    })
    assert r.status_code == 201, r.data
    assert r.data["status"] == "pending"
    dep = SchemeDependent.all_objects.get()
    # Stamped with the card's tenant: the pharmacy and the scheme read it.
    assert dep.tenant_id == world["pharm"].id and dep.enrollment == world["card"]

    # The principal reads it back; a rival scheme's seat never sees it.
    assert [d["full_name"] for d in
            portal(world["principal"]).get("/api/portal/dependents/").data] == ["Tobi Obi"]
    assert desk(world["rival_seat"]).get("/api/pharmacy/dependents/").data["count"] == 0
    assert desk(world["seat"]).get("/api/pharmacy/dependents/").data["count"] == 1

    r = desk(world["seat"]).post(f"/api/pharmacy/dependents/{dep.id}/approve/",
                                 {"member_number": "HYG-1-A"})
    assert r.status_code == 200, r.data
    dep.refresh_from_db()
    assert (dep.status, dep.member_number, dep.decided_by) == (
        "approved", "HYG-1-A", world["seat"])
    assert Notification.all_objects.filter(user=world["principal"],
                                           title="Tobi Obi approved").exists()

    # Any time later, the answer can change.
    r = desk(world["seat"]).post(f"/api/pharmacy/dependents/{dep.id}/decline/",
                                 {"reason": "Aged out of the plan."})
    assert r.status_code == 200, r.data
    dep.refresh_from_db()
    assert (dep.status, dep.reason) == ("declined", "Aged out of the plan.")
    # But not twice over.
    assert desk(world["seat"]).post(
        f"/api/pharmacy/dependents/{dep.id}/decline/", {}).status_code == 400


def test_rival_scheme_cannot_answer_and_unenrolled_patient_cannot_ask(world):
    dep = SchemeDependent.all_objects.create(
        tenant=world["pharm"], enrollment=world["card"], full_name="Tobi Obi")
    assert desk(world["rival_seat"]).post(
        f"/api/pharmacy/dependents/{dep.id}/approve/", {}).status_code == 404

    loner = User.objects.create_user("08039999999", "pw", tenant=world["pharm"],
                                     role=Role.PUBLIC)
    Patient.objects.create(tenant=world["pharm"], first_name="Bola",
                           last_name="Eze", user=loner)
    r = portal(loner).post("/api/portal/dependents/",
                           {"full_name": "X", "relationship": "child"})
    assert r.status_code == 400 and "enrollment" in r.data["errors"]
