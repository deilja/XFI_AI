import hmac
import os
import subprocess
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .key_store import create_key, delete_key, list_keys, set_active, update_limits, valid_key, consume
from .metrics import snapshot
from .providers import complete, configured_providers, detect_provider_key, test_provider_key
from .vps_manager import add_vps, audit, delete_vps, detect, list_vps, safe_restart

ADMIN_KEY = os.getenv("XFI_AI_ADMIN_KEY", "")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="XFI AI Gateway", docs_url=None, redoc_url=None)
ALLOWED_SERVICES = {"x-ui", "3x-ui", "xray", "nginx", "docker"}
OPENCLAW_ALLOWED = {
    "status": ["openclaw", "gateway", "status"],
    "models": ["openclaw", "models", "list"],
    "pairing": ["openclaw", "pairing", "list", "telegram"],
    "cron": ["openclaw", "cron", "list"],
    "heartbeat": ["openclaw", "system", "heartbeat", "last"],
}


def require_proxy_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")
    raw = authorization[7:].strip()
    if not valid_key(raw):
        raise HTTPException(401, "Invalid API key")
    if not consume(raw):
        raise HTTPException(429, "API key rate limit exceeded")
    return raw


def require_admin(key: str | None) -> None:
    if not ADMIN_KEY or not key or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")


def run_command(args: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()[-5000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


@app.get("/health")
async def health():
    return {"status": "ok", "providers": [p.name for p in configured_providers()]}


@app.get("/admin/keys")
async def admin_keys(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return {"keys": list_keys()}


@app.post("/admin/keys/{key_id}/active")
async def admin_key_active(key_id: int, request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    set_active(key_id, bool(body.get("active", True)))
    return {"ok": True}


@app.delete("/admin/keys/{key_id}")
async def admin_key_delete(key_id: int, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    delete_key(key_id)
    return {"ok": True}


@app.post("/admin/keys/{key_id}/limits")
async def admin_key_limits(key_id: int, request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    update_limits(key_id, int(body.get("rpm", 60)), int(body.get("daily", 5000)))
    return {"ok": True}


@app.get("/admin/providers")
async def admin_providers(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return {"providers": snapshot(), "configured": [p.name for p in configured_providers()]}


@app.post("/admin/providers/test")
async def admin_provider_test(request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    key = str(body.get("key", ""))
    provider = str(body.get("provider", ""))
    if not key or not provider:
        raise HTTPException(400, "provider and key are required")
    return await test_provider_key(provider, key)


@app.post("/admin/providers/detect")
async def admin_provider_detect(request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    key = str(body.get("key", ""))
    if not key:
        raise HTTPException(400, "key is required")
    return {"results": await detect_provider_key(key)}


@app.get("/admin/openclaw")
async def admin_openclaw(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    result = {}
    for name, args in OPENCLAW_ALLOWED.items():
        rc, out = run_command(args, timeout=12)
        result[name] = {"ok": rc == 0, "output": out}
    return result


@app.get("/admin/system")
async def admin_system(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    services = []
    for name in sorted(ALLOWED_SERVICES):
        rc, out = run_command(["systemctl", "is-active", name])
        services.append({"name": name, "active": rc == 0 and out.splitlines()[-1:] == ["active"], "status": out or "unknown"})
    rc, docker = run_command(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=5)
    return {"services": services, "docker": docker.splitlines() if rc == 0 and docker else []}


@app.post("/admin/system/{service}/restart")
async def admin_restart(service: str, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    if service not in ALLOWED_SERVICES:
        raise HTTPException(400, "Service is not allowed")
    rc, out = run_command(["systemctl", "restart", service], timeout=15)
    if rc != 0:
        raise HTTPException(502, f"Restart failed: {out[-1000:]}")
    rc2, state = run_command(["systemctl", "is-active", service])
    return {"ok": rc2 == 0, "service": service, "status": state}


@app.get("/admin/vps")
async def admin_vps(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return {"vps": list_vps()}


@app.post("/admin/vps")
async def admin_vps_add(request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    try:
        vid = add_vps(str(body.get("name", body.get("host", "VPS"))), str(body["host"]), int(body.get("port", 22)), str(body.get("username", "root")), str(body.get("auth_type", "key")), str(body.get("auth_value", "")))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "id": vid}


@app.delete("/admin/vps/{vps_id}")
async def admin_vps_delete(vps_id: int, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    delete_vps(vps_id)
    return {"ok": True}


@app.post("/admin/vps/{vps_id}/detect")
async def admin_vps_detect(vps_id: int, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    try:
        return detect(vps_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/admin/vps/{vps_id}/restart/{service}")
async def admin_vps_restart(vps_id: int, service: str, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    try:
        return safe_restart(vps_id, service)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/admin/audit")
async def admin_audit(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return {"audit": audit()}


@app.post("/api/keys")
async def issue_key(request: Request, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    body = await request.json()
    return {"api_key": create_key(str(body.get("name", "client")), int(body.get("rpm", 60)), int(body.get("daily", 5000))), "warning": "Save this key now. It is not stored in plaintext."}


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)):
    require_proxy_key(authorization)
    return {"object": "list", "data": [{"id": p.model, "object": "model", "owned_by": p.name} for p in configured_providers()]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    require_proxy_key(authorization)
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(413, "Request too large")
    try:
        response, provider = await complete(body)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"AI upstream error: {type(exc).__name__}") from exc
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "AI provider returned invalid JSON")
    if isinstance(data, dict):
        data.setdefault("xfi", {})["provider"] = provider
    return JSONResponse(data, status_code=response.status_code, headers={"X-XFI-AI-Provider": provider})


@app.get("/")
async def site():
    return FileResponse(WEB_DIR / "index.html")
