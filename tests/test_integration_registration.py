import os

from fastapi.testclient import TestClient

from app.api import app
from app import key_store


def test_registration_route_is_publicly_mounted():
    paths = set(app.openapi()["paths"])
    assert "/v1/integrations/register" in paths
    assert "/v1/integrations/contract" in paths


def test_registration_requires_valid_bootstrap_token(monkeypatch, tmp_path):
    monkeypatch.setenv("XFI_CONNECT_REGISTRATION_TOKEN", "bootstrap-secret")
    monkeypatch.setattr(key_store, "DB_PATH", tmp_path / "keys.db")
    client = TestClient(app)

    denied = client.post(
        "/v1/integrations/register",
        headers={"X-XFI-Registration-Token": "wrong"},
        json={"integration_id": "xfi-connect"},
    )
    assert denied.status_code == 403

    response = client.post(
        "/v1/integrations/register",
        headers={"X-XFI-Registration-Token": "bootstrap-secret"},
        json={"integration_id": "xfi-connect", "name": "XFI_CONNECT"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["integration"]["id"] == "xfi-connect"
    assert payload["api_key"].startswith("xfi_")
    assert "bootstrap-secret" not in response.text
    assert "registration_token" not in response.text.lower()
    assert key_store.valid_key(payload["api_key"])


def test_registration_rejects_unknown_integration(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_REGISTRATION_TOKEN", "bootstrap-secret")
    client = TestClient(app)
    response = client.post(
        "/v1/integrations/register",
        headers={"X-XFI-Registration-Token": "bootstrap-secret"},
        json={"integration_id": "xfi-guard"},
    )
    assert response.status_code == 403


def test_registration_uses_safe_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("XFI_3XUI_WEBAPP_REGISTRATION_TOKEN", "webapp-bootstrap")
    monkeypatch.setattr(key_store, "DB_PATH", tmp_path / "keys.db")
    client = TestClient(app)
    response = client.post(
        "/v1/integrations/register",
        headers={"X-XFI-Registration-Token": "webapp-bootstrap"},
        json={"integration_id": "xfi-3xui-webapp", "rpm": 0, "daily": 0},
    )
    assert response.status_code == 400


def test_registration_secret_is_not_part_of_integration_snapshot(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_REGISTRATION_TOKEN", "super-secret")
    response = TestClient(app).get("/admin/integrations", headers={"X-Admin-Key": os.getenv("XFI_AI_ADMIN_KEY", "")})
    assert response.status_code in {403, 200}
    if response.status_code == 200:
        assert "super-secret" not in response.text
