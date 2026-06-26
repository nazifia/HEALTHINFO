"""Runtime dev/prod toggle: cached read + admin-driven flip."""
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.embeddings import _active_provider
from apps.ai.rag import _generate
from apps.governance.models import RuntimeConfig, current_mode, is_prod


def _set_mode(mode):
    cache.clear()
    cfg = RuntimeConfig.objects.get(pk=1)
    cfg.mode = mode
    cfg.save()  # busts cache


def test_toggle_flips_mode(db):
    cache.clear()
    cfg = RuntimeConfig.objects.get(pk=1)  # seeded by migration

    cfg.mode = RuntimeConfig.Mode.PROD
    cfg.save()  # busts cache
    assert is_prod() is True
    assert current_mode() == "prod"

    cfg.mode = RuntimeConfig.Mode.DEV
    cfg.save()
    assert is_prod() is False
    assert current_mode() == "dev"


def test_singleton(db):
    cfg = RuntimeConfig(mode=RuntimeConfig.Mode.PROD)
    cfg.save()
    assert RuntimeConfig.objects.count() == 1
    assert cfg.pk == 1


@override_settings(AI_EMBED_PROVIDER="fake")
def test_embed_provider_gated_on_mode(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    _set_mode(RuntimeConfig.Mode.PROD)
    assert _active_provider() == "openai"
    _set_mode(RuntimeConfig.Mode.DEV)
    assert _active_provider() == "fake"


@override_settings(AI_EMBED_PROVIDER="fake")
def test_prod_without_key_degrades_to_fake(db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _set_mode(RuntimeConfig.Mode.PROD)
    assert _active_provider() == "fake"


@override_settings(AI_EMBED_PROVIDER="openai")
def test_explicit_provider_overrides_mode(db):
    _set_mode(RuntimeConfig.Mode.DEV)
    assert _active_provider() == "openai"


def test_gen_skipped_in_dev_even_with_key(db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _set_mode(RuntimeConfig.Mode.DEV)
    assert _generate("q", ["ctx"]) is None  # retrieval-only, no external call


def test_cors_reflects_in_dev_not_prod(db):
    origin = "http://localhost:54321"

    _set_mode(RuntimeConfig.Mode.DEV)
    resp = APIClient().get("/api/health/", HTTP_ORIGIN=origin)
    assert resp["Access-Control-Allow-Origin"] == origin

    _set_mode(RuntimeConfig.Mode.PROD)
    resp = APIClient().get("/api/health/", HTTP_ORIGIN=origin)
    assert "Access-Control-Allow-Origin" not in resp
