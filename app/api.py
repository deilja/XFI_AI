import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .key_store import create_key, valid_key

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_KEY = os.environ.get("XFI_AI_ADMIN_KEY", "")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="XFI AI Gateway", docs_url=None, redoc_url=None)


def require_proxy_key(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing API key")
    if not valid_key(authorization[7:].strip()):
        raise HTTPException(401, "Invalid API key")


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "groq", "configured": bool(GROQ_API_KEY)}


@app.post("/api/keys")
async def issue_key(request: Request, x_admin_key: str | None = Header(default=None)):
    if not ADMIN_KEY or not x_admin_key or not __import__("hmac").compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(403, "Forbidden")
    body = await request.json()
    name = str(body.get("name", "client"))
    return {"api_key": create_key(name), "warning": "Save this key now. It is not stored in plaintext."}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    require_proxy_key(authorization)
    if not GROQ_API_KEY:
        raise HTTPException(503, "Groq is not configured")
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(413, "Request too large")

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    upstream = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        response = await upstream.send(upstream.build_request("POST", GROQ_URL, content=body, headers=headers), stream=True)
    except httpx.HTTPError as exc:
        await upstream.aclose()
        raise HTTPException(502, f"Groq upstream error: {type(exc).__name__}") from exc

    async def stream():
        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()
            await upstream.aclose()

    passthrough = {"content-type": response.headers.get("content-type", "application/json")}
    return StreamingResponse(stream(), status_code=response.status_code, headers=passthrough)


@app.get("/")
async def site():
    return FileResponse(WEB_DIR / "index.html")


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse({"error": "internal_error"}, status_code=500)
