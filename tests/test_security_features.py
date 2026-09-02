import pytest

from app.providers import _key_fingerprint
from app.vps_manager import ALLOWED_SERVICES, AUTH_TYPES, add_vps


def test_key_fingerprint_does_not_equal_secret():
    key = "test-secret-key"
    assert _key_fingerprint(key) != key
    assert len(_key_fingerprint(key)) == 12


def test_vps_auth_types_exclude_password():
    assert AUTH_TYPES == {"key", "agent"}


def test_vps_service_allowlist():
    assert "xray" in ALLOWED_SERVICES
    assert "3x-ui" in ALLOWED_SERVICES
    assert "rm" not in ALLOWED_SERVICES


def test_relative_ssh_key_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        add_vps("test", "127.0.0.1", auth_type="key", auth_value="id_rsa")
