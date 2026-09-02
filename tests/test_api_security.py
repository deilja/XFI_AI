import pytest
from fastapi.testclient import TestClient

from app.api import ALLOWED_SERVICES, OPENCLAW_ALLOWED, require_admin, require_proxy_key
from app.vps_manager import _HOST_RE, _ssh_base, add_vps, safe_restart


def test_proxy_key_rejects_empty_or_oversized_credentials():
    for value in ("", "x" * 513):
        try:
            require_proxy_key(f"Bearer {value}")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 401
        else:
            raise AssertionError("invalid credential was accepted")


def test_admin_key_requires_configured_secret(monkeypatch):
    monkeypatch.setattr("app.api.ADMIN_KEY", "secret")
    try:
        require_admin("wrong")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("invalid admin credential was accepted")


def test_restart_allowlist_is_restricted():
    assert ALLOWED_SERVICES == {"x-ui", "3x-ui", "xray", "nginx", "docker"}
    assert "systemctl" not in ALLOWED_SERVICES
    assert "bash" not in ALLOWED_SERVICES


def test_openclaw_commands_are_fixed_argument_lists():
    assert OPENCLAW_ALLOWED
    for command in OPENCLAW_ALLOWED.values():
        assert command[0] == "openclaw"
        assert all(isinstance(part, str) and part for part in command)
        assert not any(";" in part or "&&" in part or "|" in part for part in command)


def test_vps_host_validation_rejects_shell_metacharacters():
    for host in ("example.com;id", "host && id", "host|id", "host$(id)", "../host"):
        assert _HOST_RE.fullmatch(host) is None


def test_vps_rejects_unsupported_auth_and_invalid_port():
    with pytest.raises(ValueError, match="auth_type"):
        add_vps("test", "127.0.0.1", auth_type="password", auth_value="secret")
    with pytest.raises(ValueError, match="port"):
        add_vps("test", "127.0.0.1", port=0, auth_type="agent")
    with pytest.raises(ValueError, match="port"):
        add_vps("test", "127.0.0.1", port=65536, auth_type="agent")


def test_ssh_base_never_embeds_a_remote_command():
    row = (1, "test", "127.0.0.1", 22, "root", "agent", "")
    args = _ssh_base(row)
    assert args[-1] == "root@127.0.0.1"
    assert "systemctl" not in args
    assert "bash" not in args


def test_safe_restart_rejects_command_injection_service():
    with pytest.raises(ValueError, match="not allowed"):
        safe_restart(1, "xray;id")


def test_api_security_headers_and_json_validation(monkeypatch):
    monkeypatch.setattr("app.api.ADMIN_KEY", "test-admin-key")
    client = TestClient(__import__("app.api", fromlist=["app"]).app)

    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    response = client.post(
        "/admin/providers/detect",
        headers={"X-Admin-Key": "test-admin-key", "Content-Type": "application/json"},
        content=b"{invalid",
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON"

    response = client.post(
        "/admin/providers/detect",
        headers={"X-Admin-Key": "test-admin-key", "Content-Type": "application/json"},
        json=["not", "an", "object"],
    )
    assert response.status_code == 400

    response = client.get("/admin/providers")
    assert response.status_code == 403
