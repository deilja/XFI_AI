"""Safe direct editor for independently installed XFI projects."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .providers import complete

MAX_FILE_BYTES = 120_000
MAX_FILES = 8
MAX_REQUEST_CHARS = 8_000
MAX_HISTORY = 12
MAX_CONTEXT_FILES = 500
SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '.cache', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'dist', 'build', '.next', '.turbo', 'coverage'}

PROJECTS = {
    "connect": {"name": "XFI_CONNECT", "path_env": "XFI_CONNECT_PATH", "default_path": "/root/XFI_CONNECT", "service_env": "XFI_CONNECT_SERVICE", "default_service": "xfi-connect", "kind": "python", "health_env": "XFI_CONNECT_HEALTH_URL", "default_health": ""},
    "webapp": {"name": "XFI_3XUI_WebApp", "path_env": "XFI_3XUI_WEBAPP_PATH", "default_path": "/opt/xfi-3xui-webapp", "service_env": "XFI_3XUI_WEBAPP_SERVICE", "default_service": "xfi-3xui-webapp", "kind": "bun", "health_env": "XFI_3XUI_WEBAPP_HEALTH_URL", "default_health": "http://127.0.0.1:3000/health"},
}

BLOCKED = (".env", "secret", "credential", "private_key", "id_rsa", ".pem", ".key")
SYSTEM_PROMPT = """Ты — инженер XFI AI. Ты работаешь только с выбранным установленным проектом XFI. Не придумывай файлы/API и не смешивай проекты. Не читай и не меняй секреты. Для анализа верни только JSON: {\"ready\":true/false,\"questions\":[...],\"summary\":\"...\",\"files\":[\"path\"]}. Если данных недостаточно, ready=false и максимум 3 конкретных вопроса."""
PATCH_PROMPT = """Сформируй минимальные изменения только для выбранного установленного проекта. Верни только JSON: {\"summary\":\"...\",\"edits\":[{\"path\":\"...\",\"content\":\"полное новое содержимое\",\"reason\":\"...\"}],\"tests\":[\"...\"]}. Только существующие безопасные файлы из контекста. Не трогай .env, secrets, credentials, private keys, сертификаты. Максимум 8 файлов. Не меняй другой проект."""


def project_config(project: str) -> dict[str, str]:
    key = project.strip().lower()
    if key not in PROJECTS:
        raise ValueError(f"Unknown project: {project}")
    cfg = PROJECTS[key].copy()
    cfg["path"] = str(Path(os.getenv(cfg["path_env"], cfg["default_path"])).resolve())
    cfg["service"] = os.getenv(cfg["service_env"], cfg["default_service"]).strip() or cfg["default_service"]
    cfg["health"] = os.getenv(cfg["health_env"], cfg["default_health"]).strip()
    return cfg


def safe_path(path: str) -> bool:
    p = path.strip().replace("\\", "/")
    return bool(p) and not p.startswith("/") and ".." not in p.split("/") and not any(x in p.lower() for x in BLOCKED)


def resolve(cfg: dict[str, str], rel: str) -> Path:
    if not safe_path(rel):
        raise ValueError(f"Unsafe path: {rel}")
    root = Path(cfg["path"])
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Path outside project: {rel}")
    return target


def files(cfg: dict[str, str]) -> dict[str, Path]:
    root = Path(cfg["path"])
    if not root.is_dir():
        raise RuntimeError(f"{cfg['name']} directory not found: {root}")
    result: dict[str, Path] = {}
    for base, dirs, filenames in os.walk(root, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(base) / filename
            try:
                rel, size = path.relative_to(root).as_posix(), path.stat().st_size
            except (OSError, ValueError):
                continue
            if safe_path(rel) and size <= MAX_FILE_BYTES:
                result[rel] = path
    return result


def read(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"File too large: {path}")
    return raw.decode("utf-8")


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("Agent response is not an object")
    return value


async def ask(messages: list[dict[str, str]]) -> str:
    body = json.dumps({"messages": messages, "temperature": 0.1, "max_tokens": 3500}).encode()
    response, _ = await complete(body)
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices")
    content = None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        content = choices[0].get("message", {}).get("content")
    elif isinstance(choices, dict):
        content = choices.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI returned no message content")
    return content


async def analyze(project: str, request: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    if not request.strip() or len(request) > MAX_REQUEST_CHARS:
        raise ValueError("Request is empty or too large")
    history = history or []
    if len(history) > MAX_HISTORY:
        raise ValueError("Too many clarification messages")
    cfg = project_config(project)
    tree = files(cfg)
    context = "\n".join(sorted(tree)[:MAX_CONTEXT_FILES])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"Выбранный проект: {cfg['name']}\nТип: {cfg['kind']}\nУстановленный путь: {cfg['path']}\nФайлы:\n{context}\n\nЗапрос:\n{request}"}]
    messages.extend(history[-MAX_HISTORY:])
    data = parse_json(await ask(messages))
    selected = [str(x) for x in data.get("files", []) if str(x) in tree and safe_path(str(x))][:MAX_FILES]
    return {"ready": bool(data.get("ready")), "questions": [str(x)[:1000] for x in data.get("questions", [])][:3], "summary": str(data.get("summary", ""))[:3000], "files": selected}


async def generate_edits(project: str, request: str, answers: list[dict[str, str]]) -> dict[str, Any]:
    analysis = await analyze(project, request, answers)
    if not analysis["ready"]:
        raise ValueError("Requirements are not complete")
    cfg = project_config(project)
    tree = files(cfg)
    selected = [p for p in analysis["files"] if p in tree]
    if not selected:
        raise ValueError("No safe existing files selected")
    context = "\n".join(f"===== {p} =====\n{read(tree[p])}" for p in selected)
    prompt = f"Проект: {cfg['name']}\nЗапрос: {request}\nУточнения: {json.dumps(answers, ensure_ascii=False)}\nПлан: {analysis['summary']}\nКонтекст:\n{context}"
    data = parse_json(await ask([{"role": "system", "content": PATCH_PROMPT}, {"role": "user", "content": prompt}]))
    raw_edits = data.get("edits", [])
    if not isinstance(raw_edits, list) or not raw_edits or len(raw_edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    safe = []
    for edit in raw_edits:
        if not isinstance(edit, dict):
            raise TypeError("Invalid edit entry")
        path, content = str(edit.get("path", "")), edit.get("content")
        if path not in selected or not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError(f"Unsafe or invalid edit: {path}")
        safe.append({"path": path, "content": content, "reason": str(edit.get("reason", ""))[:500], "expected_sha256": hashlib.sha256(read(tree[path]).encode()).hexdigest()})
    return {"project": project, "summary": str(data.get("summary", analysis["summary"]))[:3000], "edits": safe, "tests": [str(x)[:500] for x in data.get("tests", [])[:10]]}


def _run(cfg: dict[str, str], args: list[str], timeout: int) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=cfg["path"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
    return proc.returncode, proc.stdout[-12000:]


def _validate(cfg: dict[str, str], changed: list[str]) -> None:
    if cfg["kind"] == "python":
        python = shutil.which("python3") or shutil.which("python") or "python3"
        for path in changed:
            if path.endswith(".py"):
                rc, out = _run(cfg, [python, "-m", "py_compile", path], 30)
                if rc != 0:
                    raise RuntimeError(f"py_compile failed for {path}: {out[-3000:]}")
    else:
        bun = shutil.which("bun")
        if not bun:
            raise RuntimeError("bun is required for XFI_3XUI_WebApp validation")
        rc, out = _run(cfg, [bun, "run", "typecheck"], 60)
        if rc != 0:
            raise RuntimeError(f"typecheck failed: {out[-5000:]}")


def _health(cfg: dict[str, str]) -> None:
    url = cfg["health"]
    if not url:
        return
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required for health check")
    rc, out = _run(cfg, [curl, "-fsS", "--max-time", "10", url], 15)
    if rc != 0:
        raise RuntimeError(f"health check failed: {out[-3000:]}")


def apply_edits(project: str, edits: list[dict[str, str]], restart: bool = True) -> dict[str, Any]:
    if not edits or len(edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    cfg = project_config(project)
    root = Path(cfg["path"])
    lock = Path(os.getenv(f"XFI_AI_{project.upper()}_EDIT_LOCK", f"/run/lock/xfi-ai-{project}-edit.lock"))
    backup_root = Path(os.getenv("XFI_AI_BACKUP_DIR", "/var/lib/xfi-ai/backups")) / project
    import fcntl
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w", encoding="utf-8") as fd:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another {cfg['name']} edit is already running") from exc
        timestamp = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        backup_dir = backup_root / timestamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        changed: list[str] = []
        try:
            for edit in edits:
                target = resolve(cfg, edit["path"])
                if not target.is_file():
                    raise ValueError(f"File no longer exists: {edit['path']}")
                current = target.read_bytes()
                if hashlib.sha256(current).hexdigest() != edit.get("expected_sha256"):
                    raise RuntimeError(f"File changed since analysis: {edit['path']}")
                backup = backup_dir / edit["path"]
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                tmp = target.with_name(f".{target.name}.xfi-ai-{secrets.token_hex(4)}.tmp")
                tmp.write_text(edit["content"], encoding="utf-8")
                os.replace(tmp, target)
                changed.append(edit["path"])
            _validate(cfg, changed)
            if restart:
                rc, out = _run(cfg, ["systemctl", "restart", cfg["service"]], 20)
                if rc != 0:
                    raise RuntimeError(f"service restart failed: {out[-3000:]}")
                rc, state = _run(cfg, ["systemctl", "is-active", cfg["service"]], 10)
                if rc != 0 or state.strip().splitlines()[-1:] != ["active"]:
                    raise RuntimeError(f"service is not active: {state[-3000:]}")
                _health(cfg)
            return {"ok": True, "project": project, "name": cfg["name"], "backup": str(backup_dir), "changed": changed, "service": cfg["service"]}
        except Exception:
            for path in reversed(changed):
                backup = backup_dir / path
                if backup.exists():
                    shutil.copy2(backup, resolve(cfg, path))
            if restart:
                try:
                    _run(cfg, ["systemctl", "restart", cfg["service"]], 20)
                except Exception:
                    pass
            raise
        finally:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)


async def apply_edits_async(project: str, edits: list[dict[str, str]], restart: bool = True) -> dict[str, Any]:
    return await asyncio.to_thread(apply_edits, project, edits, restart)
