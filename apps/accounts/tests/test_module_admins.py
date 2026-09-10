"""Each module admins its own users.

Three portals mint their own seats: the facility's tenant admin staffs the
facility, an insurer seat flagged ``is_admin`` staffs its scheme's claims desk,
a health authority seat flagged ``is_admin`` staffs its patch. None of them can
reach out of their own module, and an unflagged seat mints nobody.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.pharmacy.models import HMO
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant

PASSWORD = "s3curepass99"


@pytest.fixture
def world(db):
    state = Jurisdiction.objects.create(name="Kano", level=Jurisdiction.Level.STATE)
    lga = Jurisdiction.objects.create(
        name="Nassarawa", level=Jurisdiction.Level.LOCAL, parent=state
    )
    other = Jurisdiction.objects.create(name="Lagos", level=Jurisdiction.Level.STATE)
    tenant = Tenant.objects.create(name="Pharm", slug="pharm", jurisdiction=lga)
    hmo = HMO.objects.create(tenant=tenant, name="Hygeia")
    rival = HMO.objects.create(tenant=tenant, name="Reliance")
    yield {"state": state, "lga": lga, "other": other, "tenant": tenant,
           "hmo": hmo, "rival": rival}
    clear_current_tenant()


def seat(**kwargs):
    user = User.objects.create(**kwargs)
    user.set_password(PASSWORD)
    user.save()
    return user


def client_for(user, tenant_slug="pharm"):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_X_TENANT_ID"] = tenant_slug
    return c


def test_tenant_admin_creates_staff_in_own_tenant(world):
    admin = seat(phone="08030000001", tenant=world["tenant"], role=Role.TENANT_ADMIN)
    resp = client_for(admin).post(
        "/api/users/",
        {"phone": "08030000002", "password": PASSWORD, "role": "pharmacist"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    made = User.objects.get(phone="08030000002")
    assert made.tenant_id == world["tenant"].id
    assert made.role == Role.PHARMACIST


def test_tenant_admin_cannot_mint_a_super_admin(world):
    admin = seat(phone="08030000003", tenant=world["tenant"], role=Role.TENANT_ADMIN)
    resp = client_for(admin).post(
        "/api/users/",
        {"phone": "08030000004", "password": PASSWORD, "role": "super_admin"},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    assert not User.objects.filter(phone="08030000004").exists()


def test_insurer_admin_mints_only_its_own_scheme(world):
    admin = seat(phone="08030000005", tenant=world["tenant"], role=Role.HMO,
                 hmo=world["hmo"], is_admin=True)
    c = client_for(admin)
    # The scheme on the body is ignored: the seat's own is pinned.
    resp = c.post(
        "/api/users/",
        {"phone": "08030000006", "password": PASSWORD, "role": "hmo",
         "hmo": world["rival"].id, "is_admin": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    made = User.objects.get(phone="08030000006")
    assert made.hmo_id == world["hmo"].id and made.is_admin

    # A pharmacist is not theirs to mint.
    assert c.post(
        "/api/users/",
        {"phone": "08030000007", "password": PASSWORD, "role": "pharmacist"},
        format="json",
    ).status_code == 400
    # And the list they read is their own desk, not the facility's staff.
    seat(phone="08030000008", tenant=world["tenant"], role=Role.PHARMACIST)
    rows = c.get("/api/users/").json()["results"]
    assert {r["phone"] for r in rows} == {"08030000005", "08030000006"}


def test_unflagged_insurer_seat_creates_nobody(world):
    plain = seat(phone="08030000009", tenant=world["tenant"], role=Role.HMO,
                 hmo=world["hmo"])
    resp = client_for(plain).post(
        "/api/users/",
        {"phone": "08030000010", "password": PASSWORD, "role": "hmo"},
        format="json",
    )
    assert resp.status_code == 403, resp.content


def test_government_admin_stays_inside_its_patch(world):
    admin = seat(phone="08030000011", role=Role.GOVERNMENT,
                 jurisdiction=world["state"], is_admin=True)
    c = client_for(admin, tenant_slug="")
    resp = c.post(
        "/api/users/",
        {"phone": "08030000012", "password": PASSWORD, "role": "government",
         "jurisdiction": world["lga"].id},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    made = User.objects.get(phone="08030000012")
    assert made.jurisdiction_id == world["lga"].id and made.tenant_id is None

    # Another state is not theirs to staff.
    assert c.post(
        "/api/users/",
        {"phone": "08030000013", "password": PASSWORD, "role": "government",
         "jurisdiction": world["other"].id},
        format="json",
    ).status_code == 400


def test_member_cannot_edit_a_colleague(world):
    seat(phone="08030000014", tenant=world["tenant"], role=Role.PHARMACIST)
    mate = seat(phone="08030000015", tenant=world["tenant"], role=Role.PHARMACIST)
    me = User.objects.get(phone="08030000014")
    resp = client_for(me).patch(
        f"/api/users/{mate.id}/", {"password": "an0therpass99"}, format="json"
    )
    assert resp.status_code == 403, resp.content


def test_grant_opens_the_user_list_to_a_pharmacist(world):
    admin = seat(phone="08030000016", tenant=world["tenant"], role=Role.TENANT_ADMIN)
    clerk = seat(phone="08030000017", tenant=world["tenant"], role=Role.PHARMACIST,
                 privileges=["manage_users"])
    resp = client_for(clerk).post(
        "/api/users/",
        {"phone": "08030000018", "password": PASSWORD, "role": "nurse",
         "license_number": "NMCN/1234"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert User.objects.get(phone="08030000018").tenant_id == world["tenant"].id
    # A grant is not the role: they cannot mint the admin who granted it.
    assert client_for(clerk).post(
        "/api/users/",
        {"phone": "08030000019", "password": PASSWORD, "role": "tenant_admin"},
        format="json",
    ).status_code == 400
    assert admin.role == Role.TENANT_ADMIN


def test_a_grant_never_exceeds_what_the_granter_holds(world):
    clerk = seat(phone="08030000020", tenant=world["tenant"], role=Role.PHARMACIST,
                 privileges=["manage_users"])
    mate = seat(phone="08030000021", tenant=world["tenant"], role=Role.PHARMACIST)
    resp = client_for(clerk).patch(
        f"/api/users/{mate.id}/",
        {"privileges": ["manage_users", "pharmacy_admin"]},
        format="json",
    )
    assert resp.status_code == 400, resp.content
    mate.refresh_from_db()
    assert mate.privileges == []

    # The tenant admin holds the whole facility catalog, so the same grant lands.
    admin = seat(phone="08030000022", tenant=world["tenant"], role=Role.TENANT_ADMIN)
    resp = client_for(admin).patch(
        f"/api/users/{mate.id}/",
        {"privileges": ["pharmacy_admin"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    mate.refresh_from_db()
    assert mate.privileges == ["pharmacy_admin"]


def test_pharmacy_admin_grant_opens_the_money_screens(world):
    from apps.accounts.permissions import is_pharmacy_admin

    plain = seat(phone="08030000023", tenant=world["tenant"], role=Role.PHARMACIST)
    trusted = seat(phone="08030000024", tenant=world["tenant"], role=Role.PHARMACIST,
                   privileges=["pharmacy_admin"])
    assert not is_pharmacy_admin(plain)
    assert is_pharmacy_admin(trusted)
    # A grant outside the seat's own module counts for nothing.
    insurer = seat(phone="08030000025", tenant=world["tenant"], role=Role.HMO,
                   hmo=world["hmo"], privileges=["pharmacy_admin"])
    assert not is_pharmacy_admin(insurer)


def test_a_member_cannot_grant_themselves_anything(world):
    plain = seat(phone="08030000026", tenant=world["tenant"], role=Role.PHARMACIST)
    resp = client_for(plain).patch(
        f"/api/users/{plain.id}/",
        {"privileges": ["pharmacy_admin"], "username": "Ada"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    plain.refresh_from_db()
    assert plain.privileges == [] and plain.username == "Ada"


def test_super_admin_registers_a_scheme_and_its_admin(world):
    """The platform signs an insurer up; the insurer then staffs itself."""
    boss = seat(phone="08030000030", role=Role.SUPER_ADMIN)
    c = APIClient()
    c.force_authenticate(user=boss)
    resp = c.post(
        "/api/pharmacy/hmos/register/",
        {
            "tenant": world["tenant"].id,
            "scheme": {"name": "AXA Mansard", "code": "AXA",
                       "coverage_percent": "80.00"},
            "admin_phone": "08030000031",
            "admin_password": PASSWORD,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    scheme = HMO.all_objects.get(name="AXA Mansard")
    assert scheme.tenant_id == world["tenant"].id
    admin = User.objects.get(phone="08030000031")
    assert (admin.role, admin.is_admin, admin.hmo_id) == (
        Role.HMO, True, scheme.id
    )

    # ...and that admin staffs the desk itself, without the pharmacy's help.
    staffed = client_for(admin).post(
        "/api/users/",
        {"phone": "08030000032", "password": PASSWORD, "role": "hmo"},
        format="json",
    )
    assert staffed.status_code == 201, staffed.content
    assert User.objects.get(phone="08030000032").hmo_id == scheme.id


def test_pharmacy_admin_cannot_register_a_scheme(world):
    admin = seat(phone="08030000033", tenant=world["tenant"],
                 role=Role.TENANT_ADMIN)
    resp = client_for(admin).post(
        "/api/pharmacy/hmos/register/",
        {"scheme": {"name": "Leadway"}, "admin_phone": "08030000034",
         "admin_password": PASSWORD},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    assert not HMO.all_objects.filter(name="Leadway").exists()
