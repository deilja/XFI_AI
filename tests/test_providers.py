import json

import httpx
import pytest

from app import providers


@pytest.mark.asyncio
async def test_complete_reports_actual_last_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("XFI_AI_PROVIDERS", "groq,gemini")

    responses = [httpx.Response(500, json={"error": "first"}), httpx.Response(500, json={"error": "second"})]

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs): return responses.pop(0)

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(providers, "_state", {})
    monkeypatch.setattr(providers, "record", lambda *args, **kwargs: None)
    response, provider = await providers.complete(json.dumps({"messages": []}).encode())
    assert response.status_code == 500
    assert provider == "gemini"


@pytest.mark.asyncio
async def test_complete_rejects_invalid_json_before_provider_call(monkeypatch):
    called = False

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("provider must not be called")

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    with pytest.raises(ValueError, match="Invalid JSON"):
        await providers.complete(b"{invalid-json")
    assert called is False


@pytest.mark.asyncio
async def test_complete_uses_capability_provider_order_and_strips_routing_metadata(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("XFI_AI_PROVIDERS", "groq,gemini")
    monkeypatch.setenv("XFI_AI_SUPPORT_PROVIDERS", "gemini,groq")

    captured = []

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, url, **kwargs):
            captured.append((url, kwargs["json"]))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(providers, "_state", {})
    monkeypatch.setattr(providers, "provider_state", lambda name: {})
    monkeypatch.setattr(providers, "record", lambda *args, **kwargs: None)
    response, provider = await providers.complete(json.dumps({"messages": [], "xfi_capability": "support"}).encode())

    assert response.status_code == 200
    assert provider == "gemini"
    assert len(captured) == 1
    assert "xfi_capability" not in captured[0][1]


@pytest.mark.asyncio
async def test_complete_rejects_unknown_capability(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported XFI capability"):
        await providers.complete(json.dumps({"messages": [], "xfi_capability": "xfi-guard"}).encode())
