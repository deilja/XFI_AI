import pytest

from app.phobos_adapter import PhobosAdapter, PhobosConfig
from app.provider_registry import providers


def test_phobos_provider_registered():
    item = next(x for x in providers() if x["id"] == "wireguard-phobos")
    assert item["kind"] == "wireguard"
    assert item["project"] == "Phobos"


def test_phobos_requires_token(monkeypatch):
    monkeypatch.delenv("XFI_PHOBOS_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        PhobosAdapter()


def test_phobos_url_is_validated():
    with pytest.raises(ValueError):
        PhobosAdapter(PhobosConfig("ftp://localhost", "token"))
