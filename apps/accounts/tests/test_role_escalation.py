"""Privilege-escalation regression: role must never be self-assignable.

Two paths that previously granted super_admin:
  1. unauthenticated POST /api/auth/register with role=super_admin
  2. authenticated PATCH /api/users/<self> with role=super_admin
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def db_clean(db):
    yield
    clear_current_tenant()


def test_register_cannot_set_super_admin(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    client = APIClient()
    resp = client.post(
        "/api/auth/register/",
        {"phone": "+2348030000001", "password": "s3curepass99", "role": "super_admin"},
        format="json",
        HTTP_X_TENANT_ID="clinic",
    )
    assert resp.status_code == 201, resp.content
    user = User.objects.get(phone="+2348030000001")
    assert user.role == Role.PUBLIC          # role ignored, forced to public
    assert user.is_super_admin is False
    assert user.tenant_id == t.id


def test_member_cannot_patch_own_role_to_super_admin(db_clean):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    user = User.objects.create(phone="+2348030000002", tenant=t, role=Role.PUBLIC)
    user.set_password("s3curepass99")
    user.save()

    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.patch(
        f"/api/users/{user.id}/",
        {"role": "super_admin"},
        format="json",
        HTTP_X_TENANT_ID="clinic",
    )
    user.refresh_from_db()
    assert user.role == Role.PUBLIC          # change dropped for non-super-admin
    assert user.is_super_admin is False
