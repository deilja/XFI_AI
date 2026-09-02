import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .metrics import record


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    key_env: str
    model_env: str
    default_model: str
    priority: int
    free: bool = False

    @property
    def key(self) -> str:
        return os.getenv(self.key_env, "")

    @property
    def model(self) -> str:
        return os.getenv(self.model_env, self.default_model)


PROVIDERS = [
    Provider("groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "GROQ_MODEL", "openai/gpt-oss-120b", 1),
    Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.5-flash", 2),
    Provider("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct", 3, True),
    Provider("openrouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openrouter/free", 4, True),
    Provider("mistral", "https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY", "MISTRAL_MODEL", "mistral-small-latest", 5),
    Provider("sambanova", "https://api.sambanova.ai/v1/chat/completions", "SAMBANOVA_API_KEY", "SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct", 6),
    Provider("cerebras", "https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY", "CEREBRAS_MODEL", "gpt-oss-120b", 7),
    Provider("huggingface", "https://router.huggingface.co/v1/chat/completions", "HF_TOKEN", "HF_MODEL", "openai/gpt-oss-120b:fastest", 8, True),
    Provider("cohere", "https://api.cohere.com/compatibility/v1/chat/completions", "COHERE_API_KEY", "COHERE_MODEL", "command-a-03-2025", 9),
]

_state: dict[str, dict[str, float]] = {}


def configured_providers() -> list[Provider]:
    requested = [x.strip().lower() for x in os.getenv("XFI_AI_PROVIDERS", ",".join(p.name for p in PROVIDERS)).split(",") if x.strip()]
    by_name = {p.name: p for p in PROVIDERS}
    return [by_name[x] for x in requested if x in by_name and by_name[x].key]


def _score(p: Provider) -> float:
    s = _state.get(p.name, {})
    cooldown = max(0.0, s.get("cooldown_until", 0) - time.time())
    if cooldown:
        return 10000 + cooldown
    return p.priority + s.get("failures", 0) * 4 + min(s.get("latency", 1.0), 20) * 0.15


def _record(p: Provider, ok: bool, latency: float, status: int | None = None) -> None:
    s = _state.setdefault(p.name, {})
    if ok:
        s["failures"] = max(0, s.get("failures", 0) - 1)
        s["latency"] = latency
        s["cooldown_until"] = 0
    else:
        s["failures"] = s.get("failures", 0) + 1
        if status in (401, 403):
            s["cooldown_until"] = time.time() + 900
        elif status == 429:
            s["cooldown_until"] = time.time() + min(300, 15 * s["failures"])
        elif status and status >= 500:
            s["cooldown_until"] = time.time() + min(60, 5 * s["failures"])
    record(p.name, ok, latency * 1000, status or 599)


def _url(p: Provider) -> str:
    if p.name == "cloudflare":
        account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        return p.url.format(account=account)
    return p.url


def _key_fingerprint(key: str) -> str:
    # Never return or log the secret. This is only a UI-safe identifier.
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()[:12]


async def test_provider_key(provider_name: str, key: str) -> dict[str, Any]:
    """Test one supplied API key without storing it.

    The request is a minimal chat completion. The response contains only
    provider/status/latency/model/fingerprint and never the supplied secret.
    """
    provider = next((p for p in PROVIDERS if p.name == provider_name.lower()), None)
    if not provider:
        return {"ok": False, "provider": provider_name, "error": "Unknown provider"}
    if not key or len(key) > 1000:
        return {"ok": False, "provider": provider.name, "error": "Invalid key input"}
    if provider.name == "cloudflare" and not os.getenv("CLOUDFLARE_ACCOUNT_ID"):
        return {"ok": False, "provider": provider.name, "error": "CLOUDFLARE_ACCOUNT_ID is required"}
    payload = {"model": provider.model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.post(
                _url(provider),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        ok = response.status_code < 400
        if ok:
            return {"ok": True, "provider": provider.name, "model": provider.model, "status": response.status_code, "latency_ms": latency_ms, "fingerprint": _key_fingerprint(key)}
        return {"ok": False, "provider": provider.name, "model": provider.model, "status": response.status_code, "latency_ms": latency_ms, "fingerprint": _key_fingerprint(key), "error": "Provider rejected the key or request"}
    except httpx.HTTPError as exc:
        return {"ok": False, "provider": provider.name, "model": provider.model, "latency_ms": round((time.monotonic() - started) * 1000, 1), "fingerprint": _key_fingerprint(key), "error": type(exc).__name__}


async def detect_provider_key(key: str) -> list[dict[str, Any]]:
    """Try the same key against every configured provider endpoint.

    No key is persisted. Results are intentionally metadata-only.
    """
    if not key or len(key) > 1000:
        return []
    results: list[dict[str, Any]] = []
    for provider in PROVIDERS:
        result = await test_provider_key(provider.name, key)
        if result.get("ok") or result.get("status") in (401, 403, 429):
            results.append(result)
    return results


async def complete(body: bytes) -> tuple[httpx.Response, str]:
    providers = sorted(configured_providers(), key=_score)
    if not providers:
        raise RuntimeError("No AI providers are configured")
    last_error: Exception | None = None
    last_response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        for provider in providers:
            started = time.monotonic()
            try:
                payload: dict[str, Any] = json.loads(body)
                payload["model"] = provider.model
                response = await client.post(_url(provider), headers={"Authorization": f"Bearer {provider.key}", "Content-Type": "application/json"}, json=payload)
                latency = time.monotonic() - started
                last_response = response
                if response.status_code < 400:
                    _record(provider, True, latency, response.status_code)
                    return response, provider.name
                if response.status_code not in (400, 401, 403, 408, 409, 429, 500, 502, 503, 504):
                    return response, provider.name
                _record(provider, False, latency, response.status_code)
            except (httpx.HTTPError, ValueError) as exc:
                latency = time.monotonic() - started
                _record(provider, False, latency)
                last_error = exc
    if last_response is not None:
        return last_response, providers[-1].name
    if last_error:
        raise last_error
    raise RuntimeError("No AI providers are available")
