import pytest

from app import project_editor


def test_project_service_override_is_rejected(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_SERVICE", "xfi-connect;systemctl")
    with pytest.raises(ValueError, match="Service is not allowed"):
        project_editor.project_config("connect")


def test_remote_health_target_is_rejected(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_HEALTH_URL", "http://example.com/health")
    with pytest.raises(ValueError, match="localhost"):
        project_editor.project_config("connect")


def test_local_health_target_is_allowed(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_HEALTH_URL", "http://127.0.0.1:8080/health")
    assert project_editor.project_config("connect")["health"] == "http://127.0.0.1:8080/health"
