"""PhobosWG provider adapter for XFI_AI.

The adapter talks to an installed Phobos instance over HTTP. It never stores
Phobos credentials in project source and never couples Phobos to XFI_CONNECT
or XFI_3XUI_WebApp.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class PhobosConfig:
    base_url: str
    token: str
    timeout: float = 10.0


def get_config() -> PhobosConfig:
    base = os.getenv("XFI_PHOBOS_URL", "http://127.0.0.1:51831").rstrip("/")
    token = os.getenv("XFI_PHOBOS_API_TOKEN", "").strip()
    if not base.startswith(("http://", "https://")):
        raise ValueError("XFI_PHOBOS_URL must use http:// or https://")
    if not token:
        raise RuntimeError("XFI_PHOBOS_API_TOKEN is not configured")
    return PhobosConfig(base_url=base, token=token)


class PhobosAdapter:
    """Small provider boundary; endpoint paths stay configurable in one place."""

    def __init__(self, config: PhobosConfig | None = None) -> None:
        self.config = config or get_config()

    def _headers(self) -> dict[str, str]:
        # Phobos deployments can front the UI with an auth gateway. Keep the
        # provider token abstract so XFI_AI does not need Phobos internals.
        return {"Authorization": f"Bearer {self.config.token}", "Accept": "application/json"}

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
        return await self._request("GET", "/api/health")

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
