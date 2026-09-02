import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("XFI_AI_ADMIN_KEY", "test-admin-key")
    monkeypatch.setenv("XFI_AI_DB", str(tmp_path / "keys.db"))
    import app.api as api
    import app.key_store as key_store
    import app.metrics as metrics
    api.ADMIN_KEY = "test-admin-key"
    key_store.DB = tmp_path / "keys.db"
    metrics.DB = tmp_path / "keys.db"
    return TestClient(api.app)


def test_admin_session_returns_short_lived_token(client):
    response = client.post("/admin/session", json={"key": "test-admin-key"})
    assert response.status_code == 200
    assert response.cookies.get("xfi_admin_session")
    assert response.headers.get("X-XFI-Admin-Session")
    assert response.json()["expires_in"] == 900


def test_admin_session_rejects_invalid_key(client):
    response = client.post("/admin/session", json={"key": "wrong"})
    assert response.status_code == 403


def test_admin_endpoint_accepts_session_token(client):
    login = client.post("/admin/session", json={"key": "test-admin-key"})
    token = login.headers["X-XFI-Admin-Session"]
    response = client.get("/admin/providers", headers={"X-Admin-Session": token})
    assert response.status_code == 200


def test_expired_admin_session_is_rejected(client, monkeypatch):
    login = client.post("/admin/session", json={"key": "test-admin-key"})
    token = login.headers["X-XFI-Admin-Session"]
    original_time = time.time
    monkeypatch.setattr("app.api.time.time", lambda: original_time() + 901)
    response = client.get("/admin/providers", headers={"X-Admin-Session": token})
    assert response.status_code == 403
