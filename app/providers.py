import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    key_env: str
    model_env: str
    default_model: str

    @property
    def key(self) -> str:
        return os.getenv(self.key_env, "")

    @property
    def model(self) -> str:
        return os.getenv(self.model_env, self.default_model)


PROVIDERS = [
    Provider("groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "GROQ_MODEL", "openai/gpt-oss-120b"),
    Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.5-flash"),
    Provider("openrouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openrouter/free"),
    Provider("mistral", "https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY", "MISTRAL_MODEL", "mistral-small-latest"),
    Provider("sambanova", "https://api.sambanova.ai/v1/chat/completions", "SAMBANOVA_API_KEY", "SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
    Provider("cerebras", "https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY", "CEREBRAS_MODEL", "gpt-oss-120b"),
    Provider("huggingface", "https://router.huggingface.co/v1/chat/completions", "HF_TOKEN", "HF_MODEL", "openai/gpt-oss-120b:fastest"),
    Provider("cohere", "https://api.cohere.com/compatibility/v1/chat/completions", "COHERE_API_KEY", "COHERE_MODEL", "command-a-03-2025"),
]


def configured_providers() -> list[Provider]:
    requested = [x.strip().lower() for x in os.getenv("XFI_AI_PROVIDERS", ",".join(p.name for p in PROVIDERS)).split(",") if x.strip()]
    by_name = {p.name: p for p in PROVIDERS}
    return [by_name[x] for x in requested if x in by_name and by_name[x].key]


async def complete(body: bytes) -> tuple[httpx.Response, str]:
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        for provider in configured_providers():
            try:
                payload: dict[str, Any] = json.loads(body)
                payload["model"] = provider.model
                response = await client.post(
                    provider.url,
                    headers={"Authorization": f"Bearer {provider.key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code < 400:
                    return response, provider.name
                if response.status_code not in (408, 409, 429, 500, 502, 503, 504):
                    return response, provider.name
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("No AI providers are configured")
