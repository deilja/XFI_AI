import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .key_store import (
    consume,
    create_key,
    delete_key,
    list_keys,
    set_active,
    update_limits,
    valid_key,
)
from .metrics import snapshot
from .providers import complete, configured_providers, detect_provider_key, test_provider_key
from .vps_manager import add_vps, audit, delete_vps, detect, list_vps, safe_restart

ADMIN_KEY = os.getenv("XFI_AI_ADMIN_KEY", "")
ADMIN_SESSION_TTL = 15 * 60
PROVIDER_DETECT_COOLDOWN = 10.0
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
_provider_detect_lock = asyncio.Lock()
_provider_detect_last = 0.0


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(SecurityHeadersMiddleware)


def _session_token(timestamp: int, nonce: str) -> str:
    payload = f"{timestamp}.{nonce}".encode()
    signature = hmac.new(ADMIN_KEY.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")


def _valid_session(token: str | None) -> bool:
    if not ADMIN_KEY or not token or len(token) > 512:
        return False
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        timestamp_b, nonce_b, signature = raw.split(b".", 2)
        timestamp = int(timestamp_b)
        if abs(time.time() - timestamp) > ADMIN_SESSION_TTL:
            return False
        payload = timestamp_b + b"." + nonce_b
        expected = hmac.new(ADMIN_KEY.encode(), payload, hashlib.sha256).digest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, TypeError, UnicodeDecodeError):
        return False


def require_admin(key: str | None, session: str | None = None) -> None:
    if _valid_session(session):
        return
    if not ADMIN_KEY or not key or len(key) != len(ADMIN_KEY) or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")


def require_proxy_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")
    raw = authorization[7:].strip()
    if not raw or len(raw) > 512 or not valid_key(raw):
        raise HTTPException(401, "Invalid API key")
    if not consume(raw):
        raise HTTPException(429, "API key rate limit exceeded")
    return raw


def run_command(args: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()[-5000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


async def read_json(request: Request, max_bytes: int = 65536) -> dict:
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(413, "JSON request too large")
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(400, "JSON body must be an object")
    return data


@app.get("/health")
async def health():
    return {"status": "ok", "providers": [p.name for p in configured_providers()]}


@app.post("/admin/session")
async def admin_session(request: Request):
    body = await read_json(request, max_bytes=4096)
    key = str(body.get("key", ""))
    if not ADMIN_KEY or not key or len(key) != len(ADMIN_KEY) or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")
    now = int(time.time())
    token = _session_token(now, secrets.token_urlsafe(24))
    response = JSONResponse({"ok": True, "expires_in": ADMIN_SESSION_TTL})
    response.set_cookie("xfi_admin_session", token, max_age=ADMIN_SESSION_TTL, httponly=True, secure=True, samesite="strict", path="/")
    response.headers["X-XFI-Admin-Session"] = token
    return response


@app.post("/admin/session/logout")
async def admin_session_logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("xfi_admin_session", path="/")
    return response


@app.get("/admin/keys")
async def admin_keys(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    return {"keys": list_keys()}


@app.post("/admin/keys/{key_id}/active")
async def admin_key_active(key_id: int, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    set_active(key_id, bool(body.get("active", True)))
    return {"ok": True}


@app.delete("/admin/keys/{key_id}")
async def admin_key_delete(key_id: int, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    delete_key(key_id)
    return {"ok": True}


@app.post("/admin/keys/{key_id}/limits")
async def admin_key_limits(key_id: int, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    try:
        rpm, daily = int(body.get("rpm", 60)), int(body.get("daily", 5000))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "rpm and daily must be integers") from exc
    if not (1 <= rpm <= 100000 and 1 <= daily <= 10000000):
        raise HTTPException(400, "limits are out of range")
    update_limits(key_id, rpm, daily)
    return {"ok": True}


@app.get("/admin/providers")
async def admin_providers(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    return {"providers": snapshot(), "configured": [p.name for p in configured_providers()]}


@app.post("/admin/providers/test")
async def admin_provider_test(request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    key = str(body.get("key", ""))
    provider = str(body.get("provider", ""))
    if not key or len(key) > 1000 or not provider or len(provider) > 100:
        raise HTTPException(400, "provider and key are required")
    return await test_provider_key(provider, key)


@app.post("/admin/providers/detect")
async def admin_provider_detect(request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    key = str(body.get("key", ""))
    if not key or len(key) > 1000:
        raise HTTPException(400, "valid key is required")
    global _provider_detect_last
    async with _provider_detect_lock:
        remaining = PROVIDER_DETECT_COOLDOWN - (time.monotonic() - _provider_detect_last)
        if remaining > 0:
            raise HTTPException(429, "Provider detection is rate limited")
        _provider_detect_last = time.monotonic()
        return {"results": await detect_provider_key(key)}


@app.get("/admin/openclaw")
async def admin_openclaw(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    result = {}
    for name, args in OPENCLAW_ALLOWED.items():
        rc, out = run_command(args, timeout=12)
        result[name] = {"ok": rc == 0, "output": out}
    return result


@app.get("/admin/system")
async def admin_system(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    services = []
    for name in sorted(ALLOWED_SERVICES):
        rc, out = run_command(["systemctl", "is-active", name])
        services.append({"name": name, "active": rc == 0 and out.splitlines()[-1:] == ["active"], "status": out or "unknown"})
    rc, docker = run_command(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"], timeout=5)
    return {"services": services, "docker": docker.splitlines() if rc == 0 and docker else []}


@app.post("/admin/system/{service}/restart")
async def admin_restart(service: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    if service not in ALLOWED_SERVICES:
        raise HTTPException(400, "Service is not allowed")
    rc, _ = run_command(["systemctl", "restart", service], timeout=15)
    if rc != 0:
        raise HTTPException(502, "Restart failed")
    rc2, state = run_command(["systemctl", "is-active", service])
    return {"ok": rc2 == 0, "service": service, "status": state}


@app.get("/admin/vps")
async def admin_vps(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    return {"vps": list_vps()}


@app.post("/admin/vps")
async def admin_vps_add(request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    try:
        vid = add_vps(str(body.get("name", body.get("host", "VPS"))), str(body["host"]), int(body.get("port", 22)), str(body.get("username", "root")), str(body.get("auth_type", "key")), str(body.get("auth_value", "")))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "id": vid}


@app.delete("/admin/vps/{vps_id}")
async def admin_vps_delete(vps_id: int, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    delete_vps(vps_id)
    return {"ok": True}


@app.post("/admin/vps/{vps_id}/detect")
async def admin_vps_detect(vps_id: int, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    try:
        return detect(vps_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/admin/vps/{vps_id}/restart/{service}")
async def admin_vps_restart(vps_id: int, service: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    try:
        return safe_restart(vps_id, service)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/admin/audit")
async def admin_audit(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    return {"audit": audit()}


@app.post("/api/keys")
async def issue_key(request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    body = await read_json(request)
    try:
        rpm, daily = int(body.get("rpm", 60)), int(body.get("daily", 5000))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "rpm and daily must be integers") from exc
    if not (1 <= rpm <= 100000 and 1 <= daily <= 10000000):
        raise HTTPException(400, "limits are out of range")
    return {"api_key": create_key(str(body.get("name", "client")), rpm, daily), "warning": "Save this key now. It is not stored in plaintext."}


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
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"AI upstream error: {type(exc).__name__}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(502, "AI provider returned invalid JSON") from exc
    if response.status_code >= 400:
        return JSONResponse(
            {"error": {"message": "AI provider request failed", "type": "upstream_error", "code": "upstream_http_error"}},
            status_code=502,
            headers={"X-XFI-AI-Provider": provider},
        )
    if isinstance(data, dict):
        data.setdefault("xfi", {})["provider"] = provider
    return JSONResponse(data, status_code=response.status_code, headers={"X-XFI-AI-Provider": provider})


@app.get("/")
async def site():
    return FileResponse(WEB_DIR / "index.html")
