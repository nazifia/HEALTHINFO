import pytest

from apps.ai.embeddings import embed
from apps.ai.indexing import index_object
from apps.ai.models import ContentEmbedding
from apps.ai.rag import semantic_search
from apps.catalog.models import Disease
from apps.tenants.current import clear_current_tenant, set_current_tenant
from apps.tenants.models import Tenant


def test_fake_embedding_is_deterministic_unit_vector(settings):
    settings.AI_EMBED_PROVIDER = "fake"
    a = embed("headache and fever")
    b = embed("headache and fever")
    assert a == b
    assert len(a) == settings.EMBED_DIM
    assert abs(sum(x * x for x in a) ** 0.5 - 1.0) < 1e-6
    # Different text -> different vector.
    assert embed("broken arm") != a


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name="Hospital A", slug="hospital-a")
    set_current_tenant(t)
    yield t
    clear_current_tenant()


def test_semantic_search_ranks_exact_match_first(tenant_a, settings):
    settings.AI_EMBED_PROVIDER = "fake"
    malaria = Disease.objects.create(
        name="Malaria", slug="malaria", description="fever chills mosquito",
        status="published",
    )
    Disease.objects.create(
        name="Fracture", slug="fracture", description="broken bone trauma",
        status="published",
    )
    for d in Disease.objects.all():
        index_object(d)

    results = semantic_search("fever chills mosquito")
    assert results[0]["object_id"] == malaria.pk
    assert results[0]["score"] > results[-1]["score"]


def test_semantic_search_is_tenant_scoped(tenant_a, settings):
    settings.AI_EMBED_PROVIDER = "fake"
    d = Disease.objects.create(
        name="Malaria", slug="malaria", description="fever", status="published"
    )
    index_object(d)

    other = Tenant.objects.create(name="Hospital B", slug="hospital-b")
    set_current_tenant(other)
    # Tenant B sees no embeddings from Tenant A.
    assert ContentEmbedding.objects.count() == 0
    assert semantic_search("fever") == []


def test_rag_degrades_to_retrieval_only_on_api_failure(tenant_a, settings, monkeypatch):
    """API error must not 500 the request: answer=None, sources still returned."""
    settings.AI_EMBED_PROVIDER = "fake"
    from apps.ai import rag

    d = Disease.objects.create(
        name="Malaria", slug="malaria", description="fever chills mosquito",
        status="published",
    )
    index_object(d)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        rag.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")),
    )

    out = rag.rag_answer("fever chills mosquito")
    assert out["answer"] is None
    assert out["sources"] and out["sources"][0]["object_id"] == d.pk


def test_rag_skips_junk_context(tenant_a, settings, monkeypatch):
    """Zero-cosine hits are not fed to the model (no fabrication from noise)."""
    settings.AI_EMBED_PROVIDER = "fake"
    from apps.ai import rag

    d = Disease.objects.create(
        name="Fracture", slug="fracture", description="broken bone trauma",
        status="published",
    )
    index_object(d)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = {}
    monkeypatch.setattr(rag, "_generate", lambda q, ctx: seen.setdefault("ctx", ctx) and "x")

    # Query shares no tokens with the only doc -> cosine 0 -> no context, no call.
    out = rag.rag_answer("unrelated query terms here")
    assert out["answer"] is None
    assert "ctx" not in seen  # _generate never called with empty context
