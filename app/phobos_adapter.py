"""Phobos provider adapter for XFI_AI.

Phobos authenticates its API with its own user/session model. XFI_AI therefore
uses HTTP Basic credentials for the provider boundary rather than inventing a
Bearer-token contract that Phobos does not expose.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class PhobosConfig:
    base_url: str
    username: str
    password: str
    timeout: float = 10.0


def get_config() -> PhobosConfig:
    base = os.getenv("XFI_PHOBOS_URL", "http://127.0.0.1:51831").rstrip("/")
    username = os.getenv("XFI_PHOBOS_USERNAME", "").strip()
    password = os.getenv("XFI_PHOBOS_PASSWORD", "")
    if not base.startswith(("http://", "https://")):
        raise ValueError("XFI_PHOBOS_URL must use http:// or https://")
    if not username or not password:
        raise RuntimeError("XFI_PHOBOS_USERNAME and XFI_PHOBOS_PASSWORD are not configured")
    return PhobosConfig(base_url=base, username=username, password=password)


class PhobosAdapter:
    """Provider boundary for an installed Phobos instance."""

    def __init__(self, config: PhobosConfig | None = None) -> None:
        self.config = config or get_config()

    def _headers(self) -> dict[str, str]:
        raw = f"{self.config.username}:{self.config.password}".encode()
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Invalid Phobos API path")
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=self.config.timeout, headers=self._headers()) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            if not response.content:
                return None
            content_type = response.headers.get("content-type", "")
            return response.json() if "json" in content_type else response.text

    async def health(self) -> Any:
        return await self._request("GET", "/api/information")

    async def clients(self) -> Any:
        return await self._request("GET", "/api/client")

    async def client(self, client_id: str) -> Any:
        return await self._request("GET", f"/api/client/{client_id}")

    async def client_config(self, client_id: str) -> Any:
        return await self._request("GET", f"/api/client/{client_id}/config")

    async def client_enable(self, client_id: str) -> Any:
        return await self._request("POST", f"/api/client/{client_id}/enable")

    async def client_disable(self, client_id: str) -> Any:
        return await self._request("POST", f"/api/client/{client_id}/disable")

    async def client_delete(self, client_id: str) -> Any:
        return await self._request("DELETE", f"/api/client/{client_id}")

    async def create_client(self, name: str, expires_at: str | None = None, preset_id: str | None = None) -> Any:
        body: dict[str, Any] = {"name": name}
        if expires_at is not None:
            body["expiresAt"] = expires_at
        if preset_id is not None:
            body["presetId"] = preset_id
        return await self._request("POST", "/api/client", json=body)

    async def install_link(self, client_id: str) -> Any:
        return await self._request("POST", f"/api/client/{client_id}/generateInstallLink")

    async def qrcode(self, client_id: str) -> str:
        return str(await self._request("GET", f"/api/client/{client_id}/qrcode.svg"))
