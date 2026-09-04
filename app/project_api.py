"""Административный API для независимо установленных проектов XFI."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from .project_audit import recent, record
from .project_editor import PROJECTS, _health, analyze, apply_edits_async, generate_edits, project_config

router = APIRouter(tags=["проекты"])


def _auth(x_admin_key: str | None, x_admin_session: str | None) -> None:
    from .api import require_admin
    require_admin(x_admin_key, x_admin_session)


async def _body(request: Request, max_bytes: int = 65536) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > max_bytes:
        raise HTTPException(413, "Запрос слишком большой")
    try:
        import json
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Некорректный JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(400, "JSON должен быть объектом")
    return value


def _project(name: str) -> str:
    name = name.strip().lower()
    if name not in PROJECTS:
        raise HTTPException(404, "Проект не найден")
    return name


@router.get("/admin/projects")
async def list_projects(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    result = []
    for key in PROJECTS:
        cfg = project_config(key)
        result.append({"id": key, "name": cfg["name"], "path": cfg["path"], "service": cfg["service"], "kind": cfg["kind"], "health_url_configured": bool(cfg["health"])})
    return {"projects": result}


@router.get("/admin/projects/audit/all")
async def all_project_audit(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    return {"audit": recent()}


@router.get("/admin/projects/{project}")
async def project_status(project: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    cfg = project_config(project)
    from .project_editor import _run
    rc, state = await asyncio.to_thread(_run, cfg, ["systemctl", "is-active", cfg["service"]], 10)
    health_ok = None
    health_error = None
    if rc == 0 and state.strip() == "active" and cfg["health"]:
        try:
            await asyncio.to_thread(_health, cfg)
            health_ok = True
        except Exception as exc:
            health_ok = False
            health_error = type(exc).__name__
    return {"id": project, "name": cfg["name"], "path": cfg["path"], "service": cfg["service"], "active": rc == 0 and state.strip().splitlines()[-1:] == ["active"], "status": state, "health": health_ok, "health_error": health_error}


@router.post("/admin/projects/{project}/analyze")
async def project_analyze(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    text = str(body.get("request", "")).strip()
    history = body.get("history", [])
    if not isinstance(history, list):
        raise HTTPException(400, "history должен быть массивом")
    try:
        result = await analyze(project, text, history)
        record("анализ", project, ready=result["ready"], files=result["files"])
        return result
    except Exception as exc:
        record("ошибка_анализа", project, error=type(exc).__name__)
        raise HTTPException(400, f"Анализ не выполнен: {type(exc).__name__}") from exc


@router.post("/admin/projects/{project}/generate")
async def project_generate(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    text = str(body.get("request", "")).strip()
    answers = body.get("answers", [])
    if not isinstance(answers, list):
        raise HTTPException(400, "answers должен быть массивом")
    try:
        result = await generate_edits(project, text, answers)
        record("подготовка_изменений", project, files=[e["path"] for e in result["edits"]])
        return result
    except Exception as exc:
        record("ошибка_подготовки", project, error=type(exc).__name__)
        raise HTTPException(400, f"Изменения не подготовлены: {type(exc).__name__}") from exc


@router.post("/admin/projects/{project}/customize")
async def project_customize(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    """Apply one natural-language customization through the guarded edit pipeline.

    Without confirm=true this endpoint only analyzes and prepares a patch. This
    keeps a natural-language request from changing a live project accidentally.
    """
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request, max_bytes=131072)
    text = str(body.get("request", "")).strip()
    answers = body.get("answers", [])
    confirm = body.get("confirm", False)
    restart = body.get("restart", True)
    if not isinstance(answers, list):
        raise HTTPException(400, "answers должен быть массивом")
    if not isinstance(confirm, bool) or not isinstance(restart, bool):
        raise HTTPException(400, "confirm и restart должны быть boolean")
    try:
        analysis = await analyze(project, text, answers)
        if not analysis["ready"]:
            record("уточнение_кастомизации", project, ready=False, files=analysis["files"])
            return {"ok": False, "stage": "questions", **analysis}
        patch = await generate_edits(project, text, answers)
        preview = {
            "ok": not confirm,
            "stage": "preview" if not confirm else "apply",
            "project": project,
            "summary": patch["summary"],
            "edits": [{"path": e["path"], "reason": e["reason"]} for e in patch["edits"]],
            "tests": patch.get("tests", []),
        }
        if not confirm:
            record("предпросмотр_кастомизации", project, files=[e["path"] for e in patch["edits"]])
            return preview
        result = await apply_edits_async(project, patch["edits"], restart=restart)
        record("кастомизация", project, files=result["changed"], backup=result["backup"], restart=restart)
        return {**preview, "ok": True, "result": result}
    except Exception as exc:
        record("ошибка_кастомизации", project, error=type(exc).__name__)
        raise HTTPException(409, f"Кастомизация не применена: {type(exc).__name__}: {exc}") from exc


@router.post("/admin/projects/{project}/apply")
async def project_apply(project: str, request: Request, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    body = await _body(request)
    if body.get("confirm") is not True:
        raise HTTPException(428, "Требуется явное подтверждение confirm=true")
    edits = body.get("edits")
    if not isinstance(edits, list):
        raise HTTPException(400, "edits должен быть массивом")
    restart = body.get("restart", True)
    if not isinstance(restart, bool):
        raise HTTPException(400, "restart должен быть boolean")
    try:
        result = await apply_edits_async(project, edits, restart=restart)
        record("применение", project, files=result["changed"], backup=result["backup"], restart=restart)
        return result
    except Exception as exc:
        record("откат", project, files=[str(e.get("path", "")) for e in edits if isinstance(e, dict)], error=type(exc).__name__)
        raise HTTPException(409, f"Изменение отклонено или отменено откатом: {type(exc).__name__}: {exc}") from exc


@router.get("/admin/projects/{project}/audit")
async def project_audit(project: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    _auth(x_admin_key, x_admin_session)
    project = _project(project)
    return {"project": project, "audit": [x for x in recent() if x.get("project") == project]}
