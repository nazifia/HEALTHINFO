"""The seats that are not a facility's staff: a patient, an insurer, a health
authority.

All three sign in to the same platform as everyone else, so the checks that
matter are the ones where the wrong row would reach the wrong desk: one insurer
must never read another's claims, a patient must never read a register of other
patients, and none of them may write anything.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.patients.models import Patient
from apps.pharmacy.models import HMO, Claim
from apps.pos.models import Sale
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Jurisdiction, Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def _client(user, tenant=None):
    c = APIClient()
    c.force_authenticate(user=user)
    c.credentials(HTTP_X_TENANT_ID=tenant.slug if tenant else "")
    return c


@pytest.fixture
def desk(db_clean):
    """One pharmacy, two schemes, one claim each, and a seat for each insurer."""
    tenant = Tenant.objects.create(name="Ade Pharmacy", slug="ade-seats")
    ours = HMO.all_objects.create(tenant=tenant, name="Ours", code="OUR")
    theirs = HMO.all_objects.create(tenant=tenant, name="Theirs", code="THR")
    for hmo, ref, amount in ((ours, "CLM-OURS", "1000.00"),
                             (theirs, "CLM-THEIRS", "2000.00")):
        sale = Sale.all_objects.create(tenant=tenant, reference=f"SL-{ref}",
                                       total=amount, hmo_payable=amount)
        Claim.all_objects.create(tenant=tenant, hmo=hmo, sale=sale,
                                 amount=amount, reference=ref)
    insurer = User.objects.create_user(phone="08030000301", password="x",
                                       tenant=tenant, role=Role.HMO, hmo=ours)
    # A health authority seat carries the patch it reads; without one the
    # platform rollups refuse it (see test_jurisdiction_scope).
    kano = Jurisdiction.objects.create(name="Kano", level="state")
    gov = User.objects.create_user(phone="08030000302", password="x",
                                   role=Role.GOVERNMENT, jurisdiction=kano)
    return tenant, ours, insurer, gov


def test_insurer_reads_only_its_own_schemes_claims(desk):
    tenant, ours, insurer, _ = desk
    res = _client(insurer, tenant).get("/api/pharmacy/claims/")
    assert res.status_code == 200
    refs = [row["reference"] for row in res.json()["results"]]
    assert refs == ["CLM-OURS"]


def test_insurer_cannot_write(desk):
    tenant, ours, insurer, _ = desk
    claim = Claim.all_objects.get(reference="CLM-OURS")
    client = _client(insurer, tenant)
    assert client.patch(f"/api/pharmacy/claims/{claim.pk}/",
                        {"reference": "HACK"}, format="json").status_code == 403
    assert client.post(f"/api/pharmacy/claims/{claim.pk}/approve/",
                       {}, format="json").status_code == 403


def test_insurer_is_shut_out_of_the_rest_of_the_tenant(desk):
    tenant, _, insurer, _ = desk
    client = _client(insurer, tenant)
    # Stock, patients and the tenant rollup are the pharmacy's, not theirs.
    assert client.get("/api/pharmacy/items/").status_code == 403
    assert client.get("/api/patients/").status_code == 403
    assert client.get("/api/analytics/tenant/").status_code == 403
    # Their own row still answers — the client asks for it on every page load.
    assert client.get("/api/users/me/").status_code == 200


def test_government_seat_reads_the_rollups_and_nothing_tenant_scoped(desk):
    tenant, _, _, gov = desk
    client = _client(gov)
    assert client.get("/api/analytics/platform/").status_code == 200
    assert client.get("/api/analytics/platform/surveillance/").status_code == 200
    assert client.get("/api/users/me/").status_code == 200
    # Inside an organization the cross-tenant views shut, same as for a
    # super-admin who opened one.
    inside = _client(gov, tenant)
    assert inside.get("/api/analytics/platform/").status_code == 403
    assert inside.get("/api/pharmacy/claims/").status_code == 403


def test_patient_reads_their_portal_not_the_registers(desk):
    tenant, _, _, _ = desk
    CaseReport.all_objects.create(tenant=tenant)
    user = User.objects.create_user(phone="08030000303", password="x",
                                    tenant=tenant, role=Role.PUBLIC)
    Patient.all_objects.create(tenant=tenant, first_name="Ada", last_name="Obi",
                               user=user)
    client = _client(user, tenant)
    # Every register is somebody else's records.
    for path in ("/api/case-reports/", "/api/adverse-reactions/",
                 "/api/lab-results/", "/api/immunizations/",
                 "/api/consultations/", "/api/prescriptions/"):
        assert client.get(path).status_code == 403, path
    # Their own history still answers, filtered to them.
    assert client.get("/api/portal/history/").status_code == 200


@pytest.fixture
def platform_admin(db_clean):
    return User.objects.create_user(phone="08030000401", password="x",
                                    role=Role.SUPER_ADMIN, is_superuser=True,
                                    is_staff=True)


def test_a_government_seat_cannot_be_bound_to_an_organization(desk, platform_admin):
    tenant, _, _, _ = desk
    res = _client(platform_admin).post("/api/users/", {
        "phone": "08030000402", "password": "sup3r-secret-pw",
        "role": Role.GOVERNMENT, "tenant": tenant.pk,
    }, format="json")
    assert res.status_code == 400
    assert "tenant" in res.json()["errors"]


def test_a_government_seat_needs_a_jurisdiction(desk, platform_admin):
    """Without one the rollups answer it nothing, so refuse the account."""
    res = _client(platform_admin).post("/api/users/", {
        "phone": "08030000405", "password": "sup3r-secret-pw",
        "role": Role.GOVERNMENT,
    }, format="json")
    assert res.status_code == 400
    assert "jurisdiction" in res.json()["errors"]


def test_an_insurer_seat_needs_a_scheme(desk, platform_admin):
    tenant, ours, _, _ = desk
    client = _client(platform_admin, tenant)
    # Without one it reads nothing, so the account is refused rather than made.
    res = client.post("/api/users/", {
        "phone": "08030000403", "password": "sup3r-secret-pw",
        "role": Role.HMO, "tenant": tenant.pk,
    }, format="json")
    assert res.status_code == 400
    assert "hmo" in res.json()["errors"]

    res = client.post("/api/users/", {
        "phone": "08030000403", "password": "sup3r-secret-pw",
        "role": Role.HMO, "tenant": tenant.pk, "hmo": ours.pk,
    }, format="json")
    assert res.status_code == 201
    assert User.objects.get(phone="08030000403").hmo_id == ours.pk


def test_an_insurer_seat_cannot_take_another_organizations_scheme(desk, platform_admin):
    tenant, _, _, _ = desk
    other = Tenant.objects.create(name="Other Pharmacy", slug="other-seats")
    theirs = HMO.all_objects.create(tenant=other, name="Theirs Only", code="TO")
    res = _client(platform_admin, tenant).post("/api/users/", {
        "phone": "08030000404", "password": "sup3r-secret-pw",
        "role": Role.HMO, "tenant": tenant.pk, "hmo": theirs.pk,
    }, format="json")
    assert res.status_code == 400
    assert "hmo" in res.json()["errors"]
