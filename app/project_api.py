"""Admin API for independently managed installed XFI projects."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from .project_editor import PROJECTS, analyze, apply_edits_async, generate_edits, project_config
from .vps_manager import audit

router = APIRouter(prefix="/admin/projects", tags=["projects"])


def _auth(x_admin_key: str | None, x_admin_session: str | None) -> None:
    from .api import require_admin
    require_admin(x_admin_key, x_admin_session)


async def _body(request: Request, max_bytes: int = 65536) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > max_bytes:
        raise HTTPException(413, "JSON request too large")
    try:
        import json
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(400, "JSON body must be an object")
    return value


def _project(name: str) -> str:
    name = name.strip().lower()
    if name not in PROJECTS:
        raise HTTPException(404, "Unknown project")
    return name


@router.get("")
async def list_projects(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    result = []
    for key in PROJECTS:
        cfg = project_config(key)
        result.append({"id": key, "name": cfg["name"], "path": cfg["path"], "service": cfg["service"], "kind": cfg["kind"], "health_url_configured": bool(cfg["health"])})
    return {"projects": result}


@router.get("/{project}")
async def project_status(project: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    cfg = project_config(project)
    from .project_editor import _run
    rc, state = await asyncio.to_thread(_run, cfg, ["systemctl", "is-active", cfg["service"]], 10)
    return {"id": project, "name": cfg["name"], "path": cfg["path"], "service": cfg["service"], "active": rc == 0 and state.strip().splitlines()[-1:] == ["active"], "status": state}


@router.post("/{project}/analyze")
async def project_analyze(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    text = str(body.get("request", "")).strip()
    history = body.get("history", [])
    if not isinstance(history, list):
        raise HTTPException(400, "history must be an array")
    try:
        return await analyze(project, text, history)
    except Exception as exc:
        raise HTTPException(400, f"Analysis failed: {type(exc).__name__}") from exc


@router.post("/{project}/generate")
async def project_generate(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    text = str(body.get("request", "")).strip()
    answers = body.get("answers", [])
    if not isinstance(answers, list):
        raise HTTPException(400, "answers must be an array")
    try:
        return await generate_edits(project, text, answers)
    except Exception as exc:
        raise HTTPException(400, f"Generation failed: {type(exc).__name__}") from exc


@router.post("/{project}/apply")
async def project_apply(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    if body.get("confirm") is not True:
        raise HTTPException(428, "Explicit confirm=true is required")
    edits = body.get("edits")
    if not isinstance(edits, list):
        raise HTTPException(400, "edits must be an array")
    restart = body.get("restart", True)
    if not isinstance(restart, bool):
        raise HTTPException(400, "restart must be boolean")
    try:
        return await apply_edits_async(project, edits, restart=restart)
    except Exception as exc:
        raise HTTPException(409, f"Project change rejected or rolled back: {type(exc).__name__}: {exc}") from exc


@router.get("/{project}/audit")
async def project_audit(project: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    _project(project)
    return {"project": project, "audit": audit()}
