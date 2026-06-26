"""Health probe: public, no auth, no tenant header, DB-backed 200."""
from rest_framework.test import APIClient


def test_health_ok(db):
    resp = APIClient().get("/api/health/")
    assert resp.status_code == 200, resp.content
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_healthz_alias_ok(db):
    assert APIClient().get("/healthz").status_code == 200
