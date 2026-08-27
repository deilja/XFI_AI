import hmac
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .key_store import create_key, valid_key

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ADMIN_KEY = os.getenv("XFI_AI_ADMIN_KEY", "")
PROVIDERS = [p.strip().lower() for p in os.getenv("XFI_AI_PROVIDERS", "groq,gemini,openrouter").split(",") if p.strip()]
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="XFI AI Gateway", docs_url=None, redoc_url=None)


def require_proxy_key(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")
    if not valid_key(authorization[7:].strip()):
        raise HTTPException(401, "Invalid API key")


def provider_config(name: str, requested_model: str | None):
    if name == "groq" and GROQ_API_KEY:
        return GROQ_URL, GROQ_API_KEY, requested_model or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    if name == "gemini" and GEMINI_API_KEY:
        return GEMINI_URL, GEMINI_API_KEY, requested_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if name == "openrouter" and OPENROUTER_API_KEY:
        return OPENROUTER_URL, OPENROUTER_API_KEY, requested_model or os.getenv("OPENROUTER_MODEL", "openrouter/free")
    return None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "providers": {
            "groq": bool(GROQ_API_KEY),
            "gemini": bool(GEMINI_API_KEY),
            "openrouter": bool(OPENROUTER_API_KEY),
        },
    }


@app.post("/api/keys")
async def issue_key(request: Request, x_admin_key: str | None = Header(default=None)):
    if not ADMIN_KEY or not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    return {"api_key": create_key(str(body.get("name", "client"))), "warning": "Save this key now. It is not stored in plaintext."}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    require_proxy_key(authorization)
    body = await request.json()
    if len(str(body).encode()) > 2 * 1024 * 1024:
        raise HTTPException(413, "Request too large")

    requested_model = body.get("model")
    # Provider is selected by XFI_AI_PROVIDERS order. A failed provider falls back to the next one.
    candidates = PROVIDERS[:]
    if requested_model and "/" in requested_model:
        prefix = requested_model.split("/", 1)[0].lower()
        if prefix in candidates:
            candidates = [prefix] + [p for p in candidates if p != prefix]

    last_error = None
    for provider in candidates:
        cfg = provider_config(provider, requested_model)
        if not cfg:
            continue
        url, api_key, model = cfg
        payload = dict(body)
        payload["model"] = model
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers.update({"HTTP-Referer": os.getenv("XFI_AI_REFERER", ""), "X-Title": "XFI AI"})
        upstream = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        try:
            response = await upstream.post(url, json=payload)
            if response.status_code < 500 and response.status_code != 429:
                data = response.json()
                data.setdefault("xfi", {})["provider"] = provider
                await upstream.aclose()
                return JSONResponse(data, status_code=response.status_code)
            last_error = f"{provider}:{response.status_code}"
        except httpx.HTTPError as exc:
            last_error = f"{provider}:{type(exc).__name__}"
        finally:
            await upstream.aclose()

    raise HTTPException(502, f"All AI providers failed: {last_error or 'no configured provider'}")


@app.get("/")
async def site():
    return FileResponse(WEB_DIR / "index.html")


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse({"error": "internal_error"}, status_code=500)
