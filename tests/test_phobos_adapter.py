import pytest

from app.phobos_adapter import PhobosAdapter, PhobosConfig, get_config
from app.phobos_api import require_phobos_admin, router
from app.provider_registry import providers


def test_phobos_provider_registered():
    item = next(x for x in providers() if x["id"] == "wireguard-phobos")
    assert item["kind"] == "wireguard"
    assert item["project"] == "Phobos"


def test_phobos_requires_credentials(monkeypatch):
    monkeypatch.delenv("XFI_PHOBOS_USERNAME", raising=False)
    monkeypatch.delenv("XFI_PHOBOS_PASSWORD", raising=False)
    with pytest.raises(RuntimeError):
        get_config()


def test_phobos_url_is_validated():
    with pytest.raises(ValueError):
        PhobosAdapter(PhobosConfig("ftp://localhost", "user", "pass"))


def test_phobos_admin_routes_are_protected():
    protected = 0
    for route in router.routes:
        dependencies = getattr(route, "dependencies", [])
        if any(getattr(dep, "dependency", None) is require_phobos_admin for dep in dependencies):
            protected += 1
    assert protected >= 1
    assert require_phobos_admin.__name__ == "require_phobos_admin"
