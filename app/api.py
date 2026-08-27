import hmac
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .key_store import create_key, valid_key
from .providers import complete, configured_providers

ADMIN_KEY = os.getenv("XFI_AI_ADMIN_KEY", "")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="XFI AI Gateway", docs_url=None, redoc_url=None)


def require_proxy_key(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")
    if not valid_key(authorization[7:].strip()):
        raise HTTPException(401, "Invalid API key")


@app.get("/health")
async def health():
    return {"status": "ok", "providers": [p.name for p in configured_providers()]}


@app.post("/api/keys")
async def issue_key(request: Request, x_admin_key: str | None = Header(default=None)):
    if not ADMIN_KEY or not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    return {"api_key": create_key(str(body.get("name", "client"))), "warning": "Save this key now. It is not stored in plaintext."}


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


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse({"error": "internal_error"}, status_code=500)
