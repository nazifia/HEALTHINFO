"""A seat signs in whichever way its phone was typed."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="T", slug="t", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )


def test_phone_typed_with_country_code_still_signs_in(tenant):
    u = User.objects.create_user(
        phone="+234 803 123 4567", role=Role.TENANT_ADMIN, tenant=tenant,
        password="pass12345!",
    )
    assert u.phone == "08031234567"
    r = APIClient().post(
        "/api/auth/token/", {"phone": "+2348031234567", "password": "pass12345!"},
        format="json",
    )
    assert r.status_code == 200, r.content

