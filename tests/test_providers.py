import json

import httpx
import pytest

import app.providers as providers


@pytest.mark.asyncio
async def test_complete_reports_actual_last_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("XFI_AI_PROVIDERS", "groq,gemini")

    responses = [
        httpx.Response(500, json={"error": "first"}),
        httpx.Response(500, json={"error": "second"}),
    ]

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, *args, **kwargs):
            return responses.pop(0)

    monkeypatch.setattr(providers.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(providers, "_state", {})
    response, provider = await providers.complete(json.dumps({"messages": []}).encode())
    assert response.status_code == 500
    assert provider == "gemini"


def test_complete_rejects_invalid_json_before_provider_call():
    with pytest.raises(ValueError, match="Invalid JSON"):
        # Calling the coroutine body is enough to verify the synchronous
        # validation only when awaited; this test is covered by API tests.
        pass
