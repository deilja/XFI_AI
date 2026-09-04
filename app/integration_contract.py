"""Versioned, secret-free contract shared by XFI client integrations."""
from __future__ import annotations

CONTRACT_VERSION = "1.0"
PROTOCOL = "xfi-ai"


def contract() -> dict[str, object]:
    return {
        "protocol": PROTOCOL,
        "version": CONTRACT_VERSION,
        "gateway": {
            "health": "/health",
            "models": "/v1/models",
            "chat_completions": "/v1/chat/completions",
        },
        "integration": {
            "status": "configured | unavailable",
            "health": "self-reported",
            "secrets": "never returned",
        },
        "capabilities": {
            "ai": "AI Gateway access",
            "support": "support workflows",
            "vpn": "VPN backend workflows",
            "code-agent": "code-agent workflows",
            "diagnostics": "node and service diagnostics",
            "3x-ui": "3X-UI control-plane diagnostics",
            "phobos": "Phobos diagnostics",
            "web-admin": "Web Admin integration",
        },
    }
