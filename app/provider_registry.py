"""Runtime registry for independent VPN providers."""
from __future__ import annotations

from typing import Any

from .phobos_adapter import PhobosAdapter


def providers() -> list[dict[str, Any]]:
    return [
        {"id": "xray-3xui", "kind": "xray", "project": "XFI_3XUI_WebApp"},
        {"id": "wireguard-phobos", "kind": "wireguard", "project": "Phobos", "configured": _phobos_configured()},
    ]


def _phobos_configured() -> bool:
    try:
        PhobosAdapter()
        return True
    except (RuntimeError, ValueError):
        return False
