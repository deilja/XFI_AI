import pytest
from starlette.requests import Request
from fastapi import HTTPException

import app.project_api as project_api


def _request(payload: dict) -> Request:
    import json

    body = json.dumps(payload).encode()
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/projects/connect/analyze",
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            "query_string": b"",
            "server": ("testserver", 443),
            "scheme": "https",
        },
        receive=lambda: {"type": "http.request", "body": body, "more_body": False},
    )


def _auth_ok(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_analyze_to_generate_contract(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    analysis = {
        "ready": True,
        "questions": [],
        "summary": "Update UI text",
        "files": ["app.py"],
        "architecture": {"node_count": 2, "edge_count": 1},
    }
    patch = {
        "project": "connect",
        "summary": "Update UI text",
        "edits": [{"path": "app.py", "content": "print('x')", "reason": "requested", "expected_sha256": "abc"}],
        "tests": ["python -m py_compile app.py"],
    }
    monkeypatch.setattr(project_api, "analyze", lambda *args, **kwargs: analysis)
    monkeypatch.setattr(project_api, "generate_edits", lambda *args, **kwargs: patch)

    analyzed = await project_api.project_analyze("connect", _request({"request": "change text"}), None, None)
    generated = await project_api.project_generate("connect", _request({"request": "change text", "answers": []}), None, None)

    assert analyzed["ready"] is True
    assert analyzed["files"] == ["app.py"]
    assert generated["edits"][0]["expected_sha256"] == "abc"


@pytest.mark.asyncio
async def test_customize_without_confirm_is_preview_only(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    analysis = {"ready": True, "questions": [], "summary": "preview", "files": ["app.py"], "architecture": {"node_count": 1, "edge_count": 0}}
    patch = {"summary": "preview", "edits": [{"path": "app.py", "reason": "test", "content": "x", "expected_sha256": "sha"}], "tests": []}
    applied = False

    monkeypatch.setattr(project_api, "analyze", lambda *args, **kwargs: analysis)
    monkeypatch.setattr(project_api, "generate_edits", lambda *args, **kwargs: patch)

    async def fail_apply(*args, **kwargs):
        nonlocal applied
        applied = True
        raise AssertionError("apply must not run during preview")

    monkeypatch.setattr(project_api, "apply_edits_async", fail_apply)
    result = await project_api.project_customize("connect", _request({"request": "preview", "confirm": False}), None, None)

    assert result["stage"] == "preview"
    assert result["ok"] is True
    assert applied is False


@pytest.mark.asyncio
async def test_apply_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)

    with pytest.raises(HTTPException) as exc:
        await project_api.project_apply("connect", _request({"edits": []}), None, None)

    assert exc.value.status_code == 428


@pytest.mark.asyncio
async def test_customize_confirmed_apply_records_result(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    analysis = {"ready": True, "questions": [], "summary": "apply", "files": ["app.py"], "architecture": {"node_count": 1, "edge_count": 0}}
    patch = {"summary": "apply", "edits": [{"path": "app.py", "reason": "test", "content": "x", "expected_sha256": "sha"}], "tests": []}
    applied = {"ok": True, "project": "connect", "backup": "/backup/test", "changed": ["app.py"], "service": "xfi-connect"}

    monkeypatch.setattr(project_api, "analyze", lambda *args, **kwargs: analysis)
    monkeypatch.setattr(project_api, "generate_edits", lambda *args, **kwargs: patch)
    monkeypatch.setattr(project_api, "apply_edits_async", lambda *args, **kwargs: applied)

    result = await project_api.project_customize("connect", _request({"request": "apply", "confirm": True, "restart": False}), None, None)

    assert result["stage"] == "apply"
    assert result["ok"] is True
    assert result["result"] == applied
