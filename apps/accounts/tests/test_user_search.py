"""Staff find a portal account by searching the user list.

Linking a patient record to its account means naming the account, and nobody
knows a user id. The list answers ?search= on what a person would type, and
still answers only for the organization asking.
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PASSWORD = "s3curepass99"


@pytest.fixture
def clinic(db):
    tenant = Tenant.objects.create(name="Clinic A", slug="clinic-a")
    yield tenant
    clear_current_tenant()


def make_user(tenant, phone, role=Role.PUBLIC, **extra):
    user = User.objects.create(phone=phone, tenant=tenant, role=role, **extra)
    user.set_password(PASSWORD)
    user.save()
    return user


def client_for(user):
    api = APIClient()
    api.force_authenticate(user)
    api.credentials(HTTP_X_TENANT_ID=user.tenant.slug)
    return api


def search(api, term):
    r = api.get("/api/users/", {"search": term})
    assert r.status_code == 200, r.content
    return [row["id"] for row in r.json()["results"]]


def test_search_narrows_the_list_by_phone_name_and_email(clinic):
    nurse = make_user(clinic, "08030000001", Role.NURSE, username="nurse-one",
                      license_number="RN/1")
    ade = make_user(clinic, "08031234567", username="ade",
                    email="ade@example.com")
    make_user(clinic, "08039999999", username="chi", email="chi@example.com")
    api = client_for(nurse)

    assert search(api, "08031234567") == [ade.id]
    assert search(api, "ade") == [ade.id]
    assert search(api, "ade@example.com") == [ade.id]


def test_search_never_reaches_another_organizations_accounts(clinic):
    other = Tenant.objects.create(name="Clinic B", slug="clinic-b")
    make_user(other, "08031234567", username="ade")
    nurse = make_user(clinic, "08030000001", Role.NURSE, username="nurse-one",
                      license_number="RN/1")

    assert search(client_for(nurse), "ade") == []
