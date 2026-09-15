"""Health probe: public, no auth, no tenant header, DB-backed 200."""
from rest_framework.test import APIClient


def test_health_ok(db):
    resp = APIClient().get("/api/health/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "ok" and body["db"] == "ok"
    # WAL on the deploy's network filesystem drops commits (config.settings);
    # the probe names the mode so a database left in WAL is visible.
    assert body["journal"] != "wal"


def test_healthz_alias_ok(db):
    assert APIClient().get("/healthz").status_code == 200
