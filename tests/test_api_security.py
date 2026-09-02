from app.api import ALLOWED_SERVICES, OPENCLAW_ALLOWED, require_admin, require_proxy_key


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
