"""Model selection and health management for the XFI AI Gateway."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    capabilities: tuple[str, ...]
    weight: int = 100


DEFAULT_MODELS: tuple[ModelProfile, ...] = (
    ModelProfile("groq", "openai/gpt-oss-120b", ("ai", "support", "code-agent"), 100),
    ModelProfile("gemini", "gemini-2.5-flash", ("ai", "support", "diagnostics"), 95),
    ModelProfile("openrouter", "openrouter/free", ("ai", "support", "code-agent", "diagnostics"), 80),
    ModelProfile("mistral", "mistral-small-latest", ("ai", "support", "code-agent"), 75),
    ModelProfile("cerebras", "gpt-oss-120b", ("ai", "support", "code-agent"), 70),
    ModelProfile("sambanova", "Meta-Llama-3.3-70B-Instruct", ("ai", "support", "code-agent"), 65),
)


class ModelManager:
    def __init__(self, profiles: tuple[ModelProfile, ...] = DEFAULT_MODELS) -> None:
        self.profiles = profiles
        self._health: dict[tuple[str, str], dict[str, float | bool]] = {}

    def candidates(self, capability: str = "ai", requested_model: str | None = None) -> list[ModelProfile]:
        capability = capability.strip().lower() or "ai"
        items = [
            p for p in self.profiles
            if capability in p.capabilities
            and (not requested_model or p.model == requested_model)
            and self._available(p)
        ]
        return sorted(items, key=self._score, reverse=True)

    def _available(self, profile: ModelProfile) -> bool:
        state = self._health.get((profile.provider, profile.model), {})
        return float(state.get("cooldown_until", 0)) <= time.time()

    def _score(self, profile: ModelProfile) -> float:
        state = self._health.get((profile.provider, profile.model), {})
        failures = float(state.get("failures", 0))
        latency = float(state.get("latency", 1.0))
        return profile.weight - failures * 15 - min(latency, 30) * 0.5

    def record(self, profile: ModelProfile, ok: bool, latency: float, status: int | None = None) -> None:
        key = (profile.provider, profile.model)
        state = self._health.setdefault(key, {})
        if ok:
            state["failures"] = max(0, float(state.get("failures", 0)) - 1)
            state["latency"] = latency
            state["cooldown_until"] = 0
            return
        failures = float(state.get("failures", 0)) + 1
        state["failures"] = failures
        state["latency"] = latency
        if status in (401, 403):
            state["cooldown_until"] = time.time() + 900
        elif status == 429:
            state["cooldown_until"] = time.time() + min(300, 15 * failures)
        elif status and status >= 500:
            state["cooldown_until"] = time.time() + min(60, 5 * failures)

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": p.provider,
                "model": p.model,
                "capabilities": list(p.capabilities),
                "weight": p.weight,
                "available": self._available(p),
            }
            for p in self.profiles
        ]


def capability_models(capability: str) -> tuple[str, ...]:
    env_name = f"XFI_AI_{capability.strip().upper().replace('-', '_')}_MODELS"
    return tuple(x.strip() for x in os.getenv(env_name, "").split(",") if x.strip())
