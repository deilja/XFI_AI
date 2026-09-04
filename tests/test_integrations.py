import pytest

from app.integrations import snapshot


def test_xfi_clients_are_first_class_integrations(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_URL", "http://127.0.0.1:8001")
    monkeypatch.setenv("XFI_CONNECT_AI_TOKEN", "xfi-connect-test")
    monkeypatch.setenv("XFI_3XUI_WEBAPP_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("XFI_3XUI_WEBAPP_AI_TOKEN", "xfi-webapp-test")

    items = {item["id"]: item for item in snapshot()}

    assert items["xfi-connect"]["configured"] is True
    assert items["xfi-connect"]["capabilities"] == ["ai", "support", "vpn", "code-agent"]
    assert items["xfi-3xui-webapp"]["configured"] is True
    assert "diagnostics" in items["xfi-3xui-webapp"]["capabilities"]


def test_integration_status_does_not_expose_urls_or_tokens(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_URL", "https://connect.example")
    monkeypatch.setenv("XFI_CONNECT_AI_TOKEN", "super-secret-token")

    item = next(x for x in snapshot() if x["id"] == "xfi-connect")

    assert "url" not in item
    assert "token" not in item
    assert item["url_configured"] is True
    assert item["token_configured"] is True


def test_invalid_integration_url_is_rejected(monkeypatch):
    monkeypatch.setenv("XFI_CONNECT_URL", "file:///etc/passwd")
    with pytest.raises(ValueError):
        snapshot()
