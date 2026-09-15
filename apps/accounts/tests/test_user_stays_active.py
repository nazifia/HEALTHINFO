"""A minted seat is live and signs in until an admin closes it — nobody else."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant

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


def login(phone, slug):
    return APIClient().post("/api/auth/token/", {"phone": phone, "password": PW},
                            format="json", HTTP_X_TENANT_ID=slug)


def test_seat_is_live_without_the_flag_and_signs_in(admin, tenant):
    r = admin.post("/api/users/", {"phone": "08031234567", "password": PW},
                   format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 201, r.content
    assert User.objects.get(phone="08031234567").is_active is True
    assert login("08031234567", tenant.slug).status_code == 200


def test_only_an_admin_closes_or_reopens_a_seat(admin, tenant):
    user = User.objects.create_user(phone="08031234567", tenant=tenant, password=PW)
    me = APIClient()
    me.force_authenticate(user)
    # A profile form echoing the flag back unticked is ignored.
    r = me.patch(f"/api/users/{user.id}/", {"is_active": False},
                 format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert r.status_code == 200, r.content
    assert login("08031234567", tenant.slug).status_code == 200
    # An admin's decision sticks, both ways.
    admin.patch(f"/api/users/{user.id}/", {"is_active": False},
                format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert login("08031234567", tenant.slug).status_code == 401
    admin.patch(f"/api/users/{user.id}/", {"is_active": True},
                format="json", HTTP_X_TENANT_ID=tenant.slug)
    assert login("08031234567", tenant.slug).status_code == 200
