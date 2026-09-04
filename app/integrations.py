"""First-class integrations exposed by the XFI AI control-plane."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .integration_contract import contract as integration_contract


@dataclass(frozen=True)
class Integration:
    id: str
    name: str
    kind: str
    description: str
    env_url: str
    env_token: str
    env_registration: str
    capabilities: tuple[str, ...]


INTEGRATIONS = (
    Integration(
        id="xfi-connect",
        name="XFI_CONNECT",
        kind="telegram_vpn_backend",
        description="Telegram VPN backend and support client for XFI AI Gateway.",
        env_url="XFI_CONNECT_URL",
        env_token="XFI_CONNECT_AI_TOKEN",  # nosec B106 - environment variable name, not a secret
        env_registration="XFI_CONNECT_REGISTRATION_TOKEN",  # nosec B106 - environment variable name, not a secret
        capabilities=("ai", "support", "vpn", "code-agent"),
    ),
    Integration(
        id="xfi-3xui-webapp",
        name="XFI_3XUI_WebApp",
        kind="web_vpn_control_plane",
        description="Telegram Mini App and Web Admin client using XFI AI for diagnostics.",
        env_url="XFI_3XUI_WEBAPP_URL",
        env_token="XFI_3XUI_WEBAPP_AI_TOKEN",  # nosec B106 - environment variable name, not a secret
        env_registration="XFI_3XUI_WEBAPP_REGISTRATION_TOKEN",  # nosec B106 - environment variable name, not a secret
        capabilities=("ai", "diagnostics", "3x-ui", "phobos", "web-admin"),
    ),
)


def get_integration(integration_id: str) -> Integration | None:
    return next((item for item in INTEGRATIONS if item.id == integration_id), None)


def registration_token_configured(integration_id: str) -> bool:
    item = get_integration(integration_id)
    return bool(item and os.getenv(item.env_registration, "").strip())


def valid_registration_token(integration_id: str, token: str) -> bool:
    item = get_integration(integration_id)
    configured = os.getenv(item.env_registration, "").strip() if item else ""
    return bool(configured and token and len(token) <= 512 and __import__("hmac").compare_digest(token, configured))


def _configured_url(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"Invalid integration URL: {name}")
    return value.rstrip("/")


def snapshot() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in INTEGRATIONS:
        url = _configured_url(item.env_url)
        result.append(
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "description": item.description,
                "configured": bool(url and os.getenv(item.env_token, "").strip()),
                "url_configured": bool(url),
                "token_configured": bool(os.getenv(item.env_token, "").strip()),
                "registration_configured": bool(os.getenv(item.env_registration, "").strip()),
                "capabilities": list(item.capabilities),
            }
        )
    return result


def contract() -> dict[str, object]:
    """Return the public, versioned integration contract without secrets."""
    return integration_contract()
