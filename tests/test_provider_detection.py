import pytest


@pytest.mark.asyncio
async def test_detect_provider_key_limits_candidates(monkeypatch):
    import app.providers as providers

    calls = []

    async def fake_test(provider_name, key):
        calls.append(provider_name)
        return {"ok": False, "provider": provider_name, "status": 401}

    monkeypatch.setattr(providers, "test_provider_key", fake_test)
    result = await providers.detect_provider_key("test-key")

    assert len(calls) == providers.DETECT_MAX_PROVIDERS
    assert result == [
        {"ok": False, "provider": name, "status": 401}
        for name in calls
    ]


@pytest.mark.asyncio
async def test_detect_provider_key_rejects_oversized_key(monkeypatch):
    import app.providers as providers

    async def fail_if_called(*args):
        raise AssertionError("provider check must not run")

    monkeypatch.setattr(providers, "test_provider_key", fail_if_called)
    assert await providers.detect_provider_key("x" * 1001) == []
