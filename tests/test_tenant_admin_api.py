"""Super-admin tenant administration: CRUD + subscription/suspend actions.

Gated to super-admins; a tenant member must never reach it. No X-Tenant-ID
header — super-admin traffic resolves no tenant (bare host)."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


@pytest.fixture
def client():
    return APIClient()


def _super(db):
    return User.objects.create_user(
        phone="08030000001", password="x", role=Role.SUPER_ADMIN,
        is_staff=True, is_superuser=True,
    )


def test_member_forbidden(db, client):
    t = Tenant.objects.create(name="Mem", slug="mem")
    member = User.objects.create_user(
        phone="08030000002", password="x", role=Role.DOCTOR, tenant=t,
    )
    client.force_authenticate(member)
    assert client.get("/api/tenants/").status_code == 403


def test_super_admin_lists_all_tenants_with_user_count(db, client):
    a = Tenant.objects.create(name="A", slug="a")
    Tenant.objects.create(name="B", slug="b")
    User.objects.create_user(phone="08030000003", password="x", tenant=a)
    client.force_authenticate(_super(db))

    resp = client.get("/api/tenants/")
    assert resp.status_code == 200
    rows = resp.json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    by_slug = {r["slug"]: r for r in rows}
    assert {"a", "b"} <= set(by_slug)
    assert by_slug["a"]["user_count"] == 1


def test_approve_and_suspend_actions(db, client):
    t = Tenant.objects.create(
        name="Pend", slug="pend",
        subscription_status=Tenant.SubscriptionStatus.PENDING,
    )
    client.force_authenticate(_super(db))

    assert client.post(f"/api/tenants/{t.id}/approve/").status_code == 200
    t.refresh_from_db()
    assert t.subscription_status == Tenant.SubscriptionStatus.APPROVED

    # suspend toggles active <-> suspended
    assert client.post(f"/api/tenants/{t.id}/suspend/").status_code == 200
    t.refresh_from_db()
    assert t.status == Tenant.Status.SUSPENDED
    client.post(f"/api/tenants/{t.id}/suspend/")
    t.refresh_from_db()
    assert t.status == Tenant.Status.ACTIVE


def test_create_tenant(db, client):
    client.force_authenticate(_super(db))
    resp = client.post(
        "/api/tenants/",
        {"name": "New Org", "slug": "new-org"},
        format="json",
    )
    assert resp.status_code == 201
    assert Tenant.objects.filter(slug="new-org").exists()


def test_super_admin_creates_user_into_tenant(db, client):
    t = Tenant.objects.create(name="Acme", slug="acme")
    client.force_authenticate(_super(db))
    resp = client.post(
        "/api/users/",
        {
            "phone": "08031112222",
            "password": "Sup3r$ecret!",
            "role": Role.DOCTOR,
            "license_number": "MDCN/54321",  # licensed cadres must carry one
            "tenant": t.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    u = User.objects.get(phone="08031112222")
    assert u.tenant_id == t.id and u.role == Role.DOCTOR
    assert u.check_password("Sup3r$ecret!")


def test_member_cannot_create_user(db, client):
    t = Tenant.objects.create(name="Mem", slug="mem2")
    admin = User.objects.create_user(
        phone="08033334444", password="x", role=Role.TENANT_ADMIN, tenant=t,
    )
    client.force_authenticate(admin)
    resp = client.post(
        "/api/users/",
        {"phone": "08035556666", "password": "Sup3r$ecret!"},
        format="json",
    )
    assert resp.status_code == 403


def test_kind_scoped_lists_are_separate(db, client):
    Tenant.objects.create(name="Gen Hosp", slug="gen", kind=Tenant.Kind.HOSPITAL)
    Tenant.objects.create(name="Corner Rx", slug="rx", kind=Tenant.Kind.PHARMACY)
    client.force_authenticate(_super(db))

    hosp = client.get("/api/tenants/hospitals/")
    pharm = client.get("/api/tenants/pharmacies/")
    assert hosp.status_code == pharm.status_code == 200
    assert [r["slug"] for r in hosp.json()["results"]] == ["gen"]
    assert [r["slug"] for r in pharm.json()["results"]] == ["rx"]
    # both still show up in the combined list
    assert {"gen", "rx"} <= {r["slug"] for r in client.get("/api/tenants/").json()["results"]}


def test_kind_lists_gated_to_super_admin(db, client):
    t = Tenant.objects.create(name="Mem", slug="mem3")
    member = User.objects.create_user(
        phone="08030000009", password="x", role=Role.DOCTOR, tenant=t,
    )
    client.force_authenticate(member)
    assert client.get("/api/tenants/hospitals/").status_code == 403


def test_backfill_guesses_hospitals_by_name(db):
    from django.core.management import call_command

    hosp = Tenant.objects.create(name="Ikeja General Hospital", slug="ikeja")
    shop = Tenant.objects.create(name="Corner Chemist", slug="corner")
    assert hosp.kind == Tenant.Kind.PHARMACY  # migrated in on the default

    call_command("backfill_tenant_kind")  # dry run changes nothing
    hosp.refresh_from_db()
    assert hosp.kind == Tenant.Kind.PHARMACY

    call_command("backfill_tenant_kind", "--apply")
    hosp.refresh_from_db()
    shop.refresh_from_db()
    assert hosp.kind == Tenant.Kind.HOSPITAL
    assert shop.kind == Tenant.Kind.PHARMACY  # no hospital word, left alone


def test_backfill_sets_named_slugs(db):
    from django.core.management import call_command

    t = Tenant.objects.create(name="St Mary's", slug="stmary")
    call_command("backfill_tenant_kind", "stmary", "--kind", "hospital", "--apply")
    t.refresh_from_db()
    assert t.kind == Tenant.Kind.HOSPITAL
