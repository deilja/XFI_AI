import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import project_api


def _request(payload: dict) -> Request:
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

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
        receive=receive,
    )


def _auth_ok(*_args, **_kwargs):
    return None


def _audit_noop(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_analyze_to_generate_contract(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    monkeypatch.setattr(project_api, "record", _audit_noop)
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

    async def fake_analyze(*args, **kwargs):
        return analysis

    async def fake_generate(*args, **kwargs):
        return patch

    monkeypatch.setattr(project_api, "analyze", fake_analyze)
    monkeypatch.setattr(project_api, "generate_edits", fake_generate)

    analyzed = await project_api.project_analyze("connect", _request({"request": "change text"}), None, None)
    generated = await project_api.project_generate("connect", _request({"request": "change text", "answers": []}), None, None)

    assert analyzed["ready"] is True
    assert analyzed["files"] == ["app.py"]
    assert analyzed["architecture"] == {"node_count": 2, "edge_count": 1}
    assert generated["edits"][0]["expected_sha256"] == "abc"
    assert generated["tests"] == ["python -m py_compile app.py"]


@pytest.mark.asyncio
async def test_customize_without_confirm_is_preview_only(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    monkeypatch.setattr(project_api, "record", _audit_noop)
    analysis = {"ready": True, "questions": [], "summary": "preview", "files": ["app.py"], "architecture": {"node_count": 1, "edge_count": 0}}
    patch = {"summary": "preview", "edits": [{"path": "app.py", "reason": "test", "content": "x", "expected_sha256": "sha"}], "tests": []}
    applied = False

    async def fake_analyze(*args, **kwargs):
        return analysis

    async def fake_generate(*args, **kwargs):
        return patch

    async def fail_apply(*args, **kwargs):
        nonlocal applied
        applied = True
        raise AssertionError("apply must not run during preview")

    monkeypatch.setattr(project_api, "analyze", fake_analyze)
    monkeypatch.setattr(project_api, "generate_edits", fake_generate)
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
async def test_apply_response_matches_android_contract(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    monkeypatch.setattr(project_api, "record", _audit_noop)
    applied = {
        "ok": True,
        "project": "connect",
        "backup": "/backup/test",
        "changed": ["app.py"],
        "service": "xfi-connect",
        "validation": {"ok": True, "tests": ["python -m py_compile app.py"]},
    }

    async def fake_apply(*args, **kwargs):
        assert kwargs["restart"] is False
        return applied

    monkeypatch.setattr(project_api, "apply_edits_async", fake_apply)
    result = await project_api.project_apply(
        "connect",
        _request(
            {
                "confirm": True,
                "restart": False,
                "edits": [{"path": "app.py", "content": "x", "reason": "test", "expected_sha256": "sha"}],
            }
        ),
        None,
        None,
    )

    assert result["ok"] is True
    assert result["project"] == "connect"
    assert result["changed"] == ["app.py"]
    assert result["backup"] == "/backup/test"
    assert result["validation"]["ok"] is True


@pytest.mark.asyncio
async def test_customize_confirmed_apply_records_result(monkeypatch):
    monkeypatch.setattr(project_api, "_auth", _auth_ok)
    monkeypatch.setattr(project_api, "record", _audit_noop)
    analysis = {"ready": True, "questions": [], "summary": "apply", "files": ["app.py"], "architecture": {"node_count": 1, "edge_count": 0}}
    patch = {"summary": "apply", "edits": [{"path": "app.py", "reason": "test", "content": "x", "expected_sha256": "sha"}], "tests": []}
    applied = {"ok": True, "project": "connect", "backup": "/backup/test", "changed": ["app.py"], "service": "xfi-connect"}

    async def fake_analyze(*args, **kwargs):
        return analysis

    async def fake_generate(*args, **kwargs):
        return patch

    async def fake_apply(*args, **kwargs):
        return applied

    monkeypatch.setattr(project_api, "analyze", fake_analyze)
    monkeypatch.setattr(project_api, "generate_edits", fake_generate)
    monkeypatch.setattr(project_api, "apply_edits_async", fake_apply)

    result = await project_api.project_customize("connect", _request({"request": "apply", "confirm": True, "restart": False}), None, None)

    assert result["stage"] == "apply"
    assert result["ok"] is True
    assert result["result"] == applied
