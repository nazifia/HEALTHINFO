"""Every relation an API answer points at comes back named, not just as a pk.

NamedRelationsMixin resolves a relation the serializer doesn't name by hand,
using the related model's own __str__ — so no client has to render "patient 41".
"""
import pytest

from apps.accounts.models import Role, User
from apps.analytics.models import CaseReport
from apps.analytics.serializers import CaseReportSerializer
from apps.catalog.models import Disease, Symptom
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_many_relation_is_named(tenant):
    disease = Disease.objects.create(name="Malaria", slug="malaria")
    symptom = Symptom.objects.create(name="Fever")
    disease.symptoms.add(symptom)

    report = CaseReport.objects.create(tenant=tenant, disease=disease)
    report.symptoms.add(symptom)

    data = CaseReportSerializer(report).data
    # The pk stays — writes still take one — with the name beside it.
    assert data["disease"] == disease.id
    assert data["disease_name"] == str(disease)
    assert data["symptoms"] == [symptom.id]
    assert data["symptoms_names"] == [str(symptom)]


def test_serializer_resolved_name_wins(tenant):
    """A relation the serializer names itself keeps its own field."""
    reporter = User.objects.create(
        phone="+2348039990001", username="Ada", tenant=tenant, role=Role.DOCTOR
    )
    data = CaseReportSerializer(
        CaseReport.objects.create(tenant=tenant, reporter=reporter)
    ).data
    assert data["reporter_name"] == "Ada"


def test_user_names_itself_by_display_name_then_phone(db):
    assert str(User(username="Ada", phone="+2348039990002")) == "Ada"
    assert str(User(phone="+2348039990002")) == "+2348039990002"
