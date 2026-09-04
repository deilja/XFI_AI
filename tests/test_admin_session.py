import time

import pytest
from fastapi.testclient import TestClient

from app import api, key_store, metrics


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("XFI_AI_ADMIN_KEY", "test-admin-key")
    monkeypatch.setenv("XFI_AI_DB", str(tmp_path / "keys.db"))
    api.ADMIN_KEY = "test-admin-key"
    key_store.DB = tmp_path / "keys.db"
    metrics.DB = tmp_path / "keys.db"
    return TestClient(api.app, base_url="https://testserver")


def test_admin_session_sets_httponly_cookie(client):
    response = client.post("/admin/session", json={"key": "test-admin-key"})
    assert response.status_code == 200
    assert response.cookies.get("xfi_admin_session")
    assert "x-xfi-admin-session" not in {k.lower() for k in response.headers.keys()}
    assert "httponly" in response.headers.get("set-cookie", "").lower()
    assert response.json()["expires_in"] == 900


def test_admin_session_rejects_invalid_key(client):
    response = client.post("/admin/session", json={"key": "wrong"})
    assert response.status_code == 403


def test_admin_endpoint_accepts_httponly_session_cookie(client):
    login = client.post("/admin/session", json={"key": "test-admin-key"})
    assert login.status_code == 200
    response = client.get("/admin/providers")
    assert response.status_code == 200


def test_admin_endpoint_rejects_forged_legacy_header(client):
    response = client.get("/admin/providers", headers={"X-Admin-Session": "forged"})
    assert response.status_code == 403


def test_expired_admin_session_is_rejected(client, monkeypatch):
    client.post("/admin/session", json={"key": "test-admin-key"})
    original_time = time.time
    monkeypatch.setattr("app.api.time.time", lambda: original_time() + 901)
    response = client.get("/admin/providers")
    assert response.status_code == 403
