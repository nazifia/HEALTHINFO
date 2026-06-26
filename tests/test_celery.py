"""Celery task logic, exercised synchronously (no broker needed)."""
import pytest

from apps.ai.models import ContentEmbedding
from apps.ai.tasks import embed_object, remove_embedding
from apps.analytics.models import AnalyticsEvent
from apps.analytics.stats import platform_stats, tenant_stats
from apps.analytics.tasks import record_event
from apps.catalog.models import Disease, Medication
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


@pytest.fixture
def tenant_a(db, settings):
    settings.AI_EMBED_PROVIDER = "fake"
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_embed_then_remove(tenant_a):
    d = Disease.objects.create(name="Malaria", slug="malaria", status="published")
    embed_object("catalog", "disease", d.pk)
    assert ContentEmbedding.objects.count() == 1
    remove_embedding("catalog", "disease", d.pk)
    assert ContentEmbedding.objects.count() == 0


def test_tenant_dashboard_aggregations(tenant_a):
    d = Disease.objects.create(name="Malaria", slug="malaria", status="published")
    Medication.objects.create(generic_name="Paracetamol", status="published")
    uid = None
    record_event(tenant_a.id, uid, "search", query="fever")
    record_event(tenant_a.id, uid, "search", query="fever")
    record_event(tenant_a.id, uid, "search", query="cough")
    record_event(tenant_a.id, uid, "view", object_type="disease", object_id=d.pk)

    stats = tenant_stats()
    assert stats["total_searches"] == 3
    assert stats["top_searches"][0] == {"query": "fever", "count": 2}
    assert stats["popular_diseases"][0]["name"] == "Malaria"
    assert stats["popular_diseases"][0]["views"] == 1


def test_platform_dashboard_counts_all_tenants(tenant_a):
    record_event(tenant_a.id, None, "search", query="x")
    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    record_event(other.id, None, "search", query="y")

    stats = platform_stats()
    assert stats["total_tenants"] == 2
    assert stats["total_searches"] == 2


def test_events_are_tenant_scoped(tenant_a):
    record_event(tenant_a.id, None, "search", query="a")
    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    set_current_tenant(other)
    assert AnalyticsEvent.objects.count() == 0  # B sees none of A's events
