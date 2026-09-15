"""A row that kept its pre-folding phone spelling still signs in with it."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant

PW = "Sup3r-Str0ng-Pw!"


@pytest.fixture
def pair(db):
    """Two rows for one number: the folded spelling taken, the other kept."""
    tenant = Tenant.objects.create(
        name="T", slug="t", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )
    User.objects.create_user(phone="08000000001", password="other",
                             role=Role.SUPER_ADMIN, is_active=False)
    legacy = User.objects.create_user(
        phone="+2348000000001", password=PW, role=Role.TENANT_ADMIN, tenant=tenant
    )
    return tenant, legacy


def login(phone, slug):
    return APIClient().post("/api/auth/token/", {"phone": phone, "password": PW},
                            format="json", HTTP_X_TENANT_ID=slug)


def test_legacy_spelling_survives_save_and_signs_in(pair):
    tenant, legacy = pair
    legacy.refresh_from_db()
    assert legacy.phone == "+2348000000001"      # not folded onto the taken row
    r = login("+2348000000001", tenant.slug)
    assert r.status_code == 200, r.content
    assert r.json()["role"] == "tenant_admin"
    # The folded spelling is the other (closed) row, as it always was.
    assert login("08000000001", tenant.slug).status_code == 401


def test_free_number_still_folds(db):
    u = User.objects.create_user(phone="+2348000000002", password=PW)
    assert u.phone == "08000000002"
