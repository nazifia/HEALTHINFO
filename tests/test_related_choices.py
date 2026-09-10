"""OPTIONS names the rows a foreign key can point at.

Without this a generated form has nothing to offer for a relation but a box to
type a raw id into. The rows offered come from the field's own queryset, so a
tenant is only ever shown its own.
"""
import pytest

from apps.analytics.serializers import CaseReportSerializer
from apps.catalog.models import Disease, Symptom
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant
from config.metadata import RelatedChoicesMetadata


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def field_info(name):
    meta = RelatedChoicesMetadata()
    return meta.get_serializer_info(CaseReportSerializer())[name]


def test_to_one_relation_is_listed(tenant):
    disease = Disease.objects.create(name="Malaria", slug="malaria")
    info = field_info("disease")
    assert {"value": disease.id, "display_name": str(disease)} in info["choices"]
    assert not info.get("multiple")


def test_to_many_relation_says_so(tenant):
    symptom = Symptom.objects.create(name="Fever")
    info = field_info("symptoms")
    assert info["multiple"] is True
    assert [c["value"] for c in info["choices"]] == [symptom.id]


def test_choices_are_sorted_by_name(tenant):
    for name in ("Zika", "Anthrax", "Measles"):
        Disease.objects.create(name=name, slug=name.lower())
    names = [c["display_name"] for c in field_info("disease")["choices"]]
    assert names == sorted(names, key=str.lower)


def test_long_relation_is_left_to_the_client(tenant, monkeypatch):
    monkeypatch.setattr("config.metadata.MAX_RELATED_CHOICES", 2)
    for i in range(3):
        Disease.objects.create(name=f"D{i}", slug=f"d{i}")
    assert "choices" not in field_info("disease")


def test_another_tenants_rows_are_not_offered(tenant):
    mine = Disease.objects.create(name="Malaria", slug="malaria")
    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    set_current_tenant(other)
    theirs = Disease.objects.create(name="Cholera", slug="cholera")
    set_current_tenant(tenant)
    values = [c["value"] for c in field_info("disease")["choices"]]
    assert mine.id in values
    assert theirs.id not in values
