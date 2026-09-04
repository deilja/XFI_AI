"""Административные API независимых VPN-провайдеров и проектов XFI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .phobos_adapter import PhobosAdapter
from .project_api import router as project_router


def require_phobos_admin(request: Request) -> None:
    from .api import require_admin
    require_admin(request.headers.get("x-xfi-admin-key"), request.headers.get("x-xfi-admin-session"))


router = APIRouter(prefix="/admin/phobos", tags=["phobos"], dependencies=[Depends(require_phobos_admin)])
router.include_router(project_router)


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: str | None = Field(default=None, max_length=64)
    preset_id: str | None = Field(default=None, max_length=128)


@router.get("/health")
async def health():
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().health()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Проверка Phobos не выполнена: {type(exc).__name__}") from exc


@router.get("/clients")
async def clients():
    try:
        return {"ok": True, "provider": "phobos", "clients": await PhobosAdapter().clients()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Список клиентов Phobos недоступен: {type(exc).__name__}") from exc


@router.post("/clients")
async def create_client(body: ClientCreate):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().create_client(body.name, body.expires_at, body.preset_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось создать клиента Phobos: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Клиент Phobos недоступен: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}/config")
async def client_config(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_config(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Конфигурация Phobos недоступна: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/enable")
async def enable(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_enable(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось включить клиента: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/disable")
async def disable(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_disable(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось отключить клиента: {type(exc).__name__}") from exc


@router.delete("/clients/{client_id}")
async def delete(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().client_delete(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Не удалось удалить клиента: {type(exc).__name__}") from exc


@router.post("/clients/{client_id}/install-link")
async def install_link(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "result": await PhobosAdapter().install_link(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Install Link Phobos недоступен: {type(exc).__name__}") from exc


@router.get("/clients/{client_id}/qrcode")
async def qrcode(client_id: str):
    try:
        return {"ok": True, "provider": "phobos", "svg": await PhobosAdapter().qrcode(client_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"QR-код Phobos недоступен: {type(exc).__name__}") from exc
