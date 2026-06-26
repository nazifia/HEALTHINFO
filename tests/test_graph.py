"""Knowledge-graph relations: linking, traversal, cross-tenant guard."""
import pytest
from django.core.exceptions import ValidationError

from apps.catalog.models import Disease, DrugInteraction, Medication, Symptom
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_disease_symptom_medication_links(tenant_a):
    fever = Symptom.objects.create(name="Fever", severity_level=2)
    para = Medication.objects.create(generic_name="Paracetamol")
    malaria = Disease.objects.create(name="Malaria", slug="malaria")
    malaria.symptoms.add(fever)
    malaria.medications.add(para)

    assert list(fever.diseases.all()) == [malaria]
    assert list(para.diseases.all()) == [malaria]


def test_related_diseases_share_symptom(tenant_a):
    fever = Symptom.objects.create(name="Fever")
    malaria = Disease.objects.create(name="Malaria", slug="malaria")
    flu = Disease.objects.create(name="Flu", slug="flu")
    malaria.symptoms.add(fever)
    flu.symptoms.add(fever)

    related = (
        Disease.objects.filter(symptoms__in=malaria.symptoms.all())
        .exclude(pk=malaria.pk)
        .distinct()
    )
    assert list(related) == [flu]


def test_drug_interaction_edge(tenant_a):
    a = Medication.objects.create(generic_name="Warfarin")
    b = Medication.objects.create(generic_name="Aspirin")
    DrugInteraction.objects.create(
        medication_a=a, medication_b=b, severity="major"
    )
    assert a.interactions_a.count() == 1
    assert b.interactions_b.count() == 1


def test_interaction_self_link_rejected(tenant_a):
    a = Medication.objects.create(generic_name="Warfarin")
    with pytest.raises(ValidationError):
        DrugInteraction.objects.create(medication_a=a, medication_b=a, severity="minor")


def test_interaction_cross_tenant_rejected(tenant_a):
    a = Medication.objects.create(generic_name="Warfarin")
    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    set_current_tenant(other)
    b = Medication.objects.create(generic_name="Aspirin")
    set_current_tenant(tenant_a)
    with pytest.raises(ValidationError):
        DrugInteraction.objects.create(medication_a=a, medication_b=b, severity="minor")


def _req(role):
    from types import SimpleNamespace

    return SimpleNamespace(user=SimpleNamespace(is_authenticated=True, role=role))


def test_graph_hides_unpublished_from_public(tenant_a):
    """PUBLIC role must not see draft content via graph traversal (was leaking)."""
    from apps.accounts.models import Role
    from apps.catalog.graph import _pub

    Disease.objects.create(name="Pub", slug="pub", status="published")
    Disease.objects.create(name="Draft", slug="draft", status="draft")

    public = _pub(_req(Role.PUBLIC), Disease.objects.all())
    assert {d.name for d in public} == {"Pub"}

    staff = _pub(_req(Role.DOCTOR), Disease.objects.all())
    assert {d.name for d in staff} == {"Pub", "Draft"}
