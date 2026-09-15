"""signin_audit names the refused seats and leaves every password as it was."""
from io import StringIO

from django.core.management import call_command

from apps.accounts.models import Role, User
from apps.tenants.models import Tenant


def test_audit_reports_the_closed_seat_and_changes_nothing(db):
    tenant = Tenant.objects.create(
        name="T", slug="t", subscription_status=Tenant.SubscriptionStatus.APPROVED
    )
    ok = User.objects.create_user(phone="08031234567", password="keep-me-1", tenant=tenant)
    User.objects.create_user(phone="08031234568", password="x", tenant=tenant,
                             role=Role.PHARMACIST, is_active=False)
    out = StringIO()
    call_command("signin_audit", stdout=out)
    text = out.getvalue()
    assert "1/2 seats sign in." in text and "08031234568" in text and "closed" in text
    ok.refresh_from_db()
    assert ok.check_password("keep-me-1")
