"""Admin API helpers for the independent Phobos provider."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .phobos_adapter import PhobosAdapter

router = APIRouter(prefix="/admin/phobos", tags=["phobos"], dependencies=[Depends(require_phobos_admin)])


def require_phobos_admin(request: Request) -> None:
    # Lazy import avoids a circular import: app.api owns the FastAPI application.
    from .api import require_admin
    require_admin(request.headers.get("x-xfi-admin-key"), request.headers.get("x-xfi-admin-session"))


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: str | None = Field(default=None, max_length=64)
    preset_id: str | None = Field(default=None, max_length=128)


class ClientAction(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)


@router.get("/health")
async def health():
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().health()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos health failed: {type(exc).__name__}") from exc


@router.get("/clients")
async def clients():
    try:
        return {"ok": True, "provider": "phobos", "clients": await PhobosAdapter().clients()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos clients failed: {type(exc).__name__}") from exc


@router.post("/clients")
async def create_client(body: ClientCreate):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().create_client(body.name, body.expires_at, body.preset_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos create failed: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos client failed: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}/config")
async def client_config(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_config(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos config failed: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/enable")
async def enable(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_enable(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos enable failed: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/disable")
async def disable(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_disable(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos disable failed: {type(exc).__name__}") from exc


@router.delete("/clients/{client_id}")
async def delete(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_delete(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos delete failed: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/install-link")
async def install_link(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().install_link(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos install-link failed: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}/qrcode")
async def qrcode(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "svg": await PhobosAdapter().qrcode(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Phobos QR failed: {type(exc).__name__}") from exc
