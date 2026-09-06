"""The roster: who is on duty is read off shifts, not typed into a report."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.analytics.models import FacilityMetric
from apps.branches.models import Branch, Shift
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(
        name="Hospital A", slug="hospital-a",
        subscription_status=Tenant.SubscriptionStatus.APPROVED,
    )
    set_current_tenant(t)
    yield t
    clear_current_tenant()


_PHONE = iter(f"080000000{n:02d}" for n in range(10, 99))


@pytest.fixture
def reporter(tenant_a, client):
    """Signed in as somebody who may read the roster."""
    user = _user(tenant_a, "reader")
    client.force_authenticate(user)
    return user


@pytest.fixture
def client():
    return APIClient()


def _user(tenant, name):
    return User.objects.create_user(
        username=name, phone=next(_PHONE), password="x",
        tenant=tenant, role=Role.NURSE,
    )


def _shift(user, branch, start, end):
    return Shift.objects.create(
        user=user, branch=branch, starts_at=start, ends_at=end
    )


def test_on_duty_counts_only_the_covering_shifts(tenant_a):
    branch = Branch.all_objects.get(tenant=tenant_a)
    now = timezone.now()
    on = _user(tenant_a, "on-now")
    earlier = _user(tenant_a, "went-home")
    later = _user(tenant_a, "not-in-yet")
    _shift(on, branch, now - timedelta(hours=1), now + timedelta(hours=7))
    _shift(earlier, branch, now - timedelta(hours=9), now - timedelta(hours=1))
    _shift(later, branch, now + timedelta(hours=7), now + timedelta(hours=15))

    assert list(Shift.on_duty(at=now).values_list("user", flat=True)) == [on.pk]
    assert Shift.count_on_duty(at=now) == 1


def test_handover_does_not_double_count(tenant_a):
    """A shift ending at 14:00 and one starting at 14:00 overlap nowhere."""
    branch = Branch.all_objects.get(tenant=tenant_a)
    handover = timezone.now()
    morning = _user(tenant_a, "morning")
    afternoon = _user(tenant_a, "afternoon")
    _shift(morning, branch, handover - timedelta(hours=6), handover)
    _shift(afternoon, branch, handover, handover + timedelta(hours=6))

    assert Shift.count_on_duty(at=handover) == 1


def test_double_booking_counts_one_person(tenant_a):
    branch = Branch.all_objects.get(tenant=tenant_a)
    now = timezone.now()
    both = _user(tenant_a, "double-booked")
    _shift(both, branch, now - timedelta(hours=2), now + timedelta(hours=2))
    _shift(both, branch, now - timedelta(hours=1), now + timedelta(hours=3))

    assert Shift.on_duty(at=now).count() == 2
    assert Shift.count_on_duty(at=now) == 1


def test_shifts_are_tenant_scoped(tenant_a):
    branch = Branch.all_objects.get(tenant=tenant_a)
    _shift(_user(tenant_a, "ours"), branch,
           timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1))
    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    set_current_tenant(other)

    assert Shift.count_on_duty() == 0


def test_blank_staffing_falls_back_to_the_roster(tenant_a):
    branch = Branch.all_objects.get(tenant=tenant_a)
    now = timezone.now()
    _shift(_user(tenant_a, "on-a"), branch, now - timedelta(hours=1),
           now + timedelta(hours=7))
    _shift(_user(tenant_a, "on-b"), branch, now - timedelta(hours=1),
           now + timedelta(hours=7))

    m = FacilityMetric.objects.create(beds_total=10, patients_treated=4)
    assert m.staff_on_duty == 2


def test_a_typed_staffing_number_wins(tenant_a):
    branch = Branch.all_objects.get(tenant=tenant_a)
    now = timezone.now()
    _shift(_user(tenant_a, "rostered"), branch, now - timedelta(hours=1),
           now + timedelta(hours=7))

    m = FacilityMetric.objects.create(staff_on_duty=5, patients_treated=4)
    assert m.staff_on_duty == 5

    # Editing it back to 0 is an answer, not a blank — the roster stays out.
    m.staff_on_duty = 0
    m.save()
    m.refresh_from_db()
    assert m.staff_on_duty == 0


def test_the_week_window_filters_by_when_a_shift_starts(tenant_a):
    """?starts_at__gte=&starts_at__lt= is what the calendar week asks for."""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.branches.views import ShiftViewSet

    branch = Branch.all_objects.get(tenant=tenant_a)
    monday = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    inside = _shift(_user(tenant_a, "this-week"), branch,
                    monday + timedelta(days=1), monday + timedelta(days=1, hours=8))
    _shift(_user(tenant_a, "next-week"), branch,
           monday + timedelta(days=8), monday + timedelta(days=8, hours=8))

    admin = User.objects.create_user(
        username="roster-admin", phone=next(_PHONE), password="x",
        tenant=tenant_a, role=Role.TENANT_ADMIN,
    )
    req = APIRequestFactory().get("/api/shifts/", {
        "starts_at__gte": monday.isoformat(),
        "starts_at__lt": (monday + timedelta(days=7)).isoformat(),
    })
    req.tenant = tenant_a
    force_authenticate(req, user=admin)
    res = ShiftViewSet.as_view({"get": "list"})(req)

    assert res.status_code == 200
    assert [r["id"] for r in res.data["results"]] == [inside.pk]


def test_the_week_view_gets_only_its_week(tenant_a, client, reporter):
    """The roster's week view filters server-side; unknown params would be
    dropped silently and hand it the whole roster instead."""
    branch = Branch.all_objects.get(tenant=tenant_a)
    monday = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    user = _user(tenant_a, "rostered")
    _shift(user, branch, monday, monday + timedelta(hours=8))
    _shift(user, branch, monday + timedelta(days=14),
           monday + timedelta(days=14, hours=8))

    resp = client.get("/api/shifts/", {
        "starts_at__gte": monday.isoformat(),
        "starts_at__lt": (monday + timedelta(days=7)).isoformat(),
    }, HTTP_X_TENANT_ID="hospital-a")
    assert resp.status_code == 200
    rows = resp.json()["results"]
    assert len(rows) == 1
    # The card prints the branch by name; "" when the shift is facility-wide.
    assert rows[0]["branch_name"] == branch.name
    assert rows[0]["username"] == "rostered"


def test_a_facility_wide_shift_has_a_blank_branch_name(tenant_a, client, reporter):
    now = timezone.now()
    _shift(_user(tenant_a, "anywhere"), None, now - timedelta(hours=1),
           now + timedelta(hours=7))

    resp = client.get("/api/shifts/", HTTP_X_TENANT_ID="hospital-a")
    assert resp.json()["results"][0]["branch_name"] == ""


def test_only_the_tenant_admin_writes_the_roster(tenant_a, client, reporter):
    """A nurse reads who is on; putting somebody on is the admin's."""
    branch = Branch.all_objects.get(tenant=tenant_a)
    now = timezone.now()
    body = {
        "user": reporter.pk,
        "branch": branch.pk,
        "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(hours=8)).isoformat(),
    }

    assert client.post("/api/shifts/", body,
                       HTTP_X_TENANT_ID="hospital-a").status_code == 403

    admin = User.objects.create_user(
        username="roster-owner", phone=next(_PHONE), password="x",
        tenant=tenant_a, role=Role.TENANT_ADMIN,
    )
    client.force_authenticate(admin)
    assert client.post("/api/shifts/", body,
                       HTTP_X_TENANT_ID="hospital-a").status_code == 201


def test_a_shift_that_ends_before_it_starts_is_refused(tenant_a, client):
    admin = User.objects.create_user(
        username="roster-clock", phone=next(_PHONE), password="x",
        tenant=tenant_a, role=Role.TENANT_ADMIN,
    )
    client.force_authenticate(admin)
    now = timezone.now()

    resp = client.post("/api/shifts/", {
        "user": admin.pk,
        "starts_at": now.isoformat(),
        "ends_at": (now - timedelta(hours=1)).isoformat(),
    }, HTTP_X_TENANT_ID="hospital-a")
    assert resp.status_code == 400
