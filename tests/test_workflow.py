"""Draft -> Review -> Approved -> Published lifecycle + audit log + role gates."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role, User
from apps.catalog.models import Disease
from apps.governance.models import AuditLog
from apps.governance.workflow import perform_transition
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def env(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    doctor = User.objects.create(phone="+2348038880001", tenant=t, role=Role.DOCTOR)
    admin = User.objects.create(phone="+2348038880002", tenant=t, role=Role.TENANT_ADMIN)
    disease = Disease.objects.create(name="Malaria", slug="malaria")  # status=draft
    yield doctor, admin, disease
    clear_current_tenant()


def test_full_happy_path(env):
    doctor, admin, d = env
    perform_transition(d, doctor, "review")
    assert d.status == "review"
    perform_transition(d, doctor, "approved")   # doctor = reviewer
    assert d.status == "approved"
    perform_transition(d, admin, "published")   # admin = editor
    assert d.status == "published"
    # Every step logged.
    assert AuditLog.objects.count() == 3
    assert list(AuditLog.objects.values_list("to_status", flat=True)) == [
        "published", "approved", "review",  # ordering = -created_at
    ]


def test_illegal_edge_rejected(env):
    _, admin, d = env
    with pytest.raises(ValidationError):
        perform_transition(d, admin, "published")  # draft -> published not allowed


def test_role_gate(env):
    doctor, _, d = env
    perform_transition(d, doctor, "review")
    perform_transition(d, doctor, "approved")
    with pytest.raises(PermissionDenied):
        perform_transition(d, doctor, "published")  # doctor is not an editor
    assert d.status == "approved"
