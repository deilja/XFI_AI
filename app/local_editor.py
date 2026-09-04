"""Safe direct editor for an installed XFI_CONNECT deployment."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import py_compile
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
MAX_ANSWERS = 12
BACKUP_ROOT = Path(os.getenv("XFI_AI_BACKUP_DIR", "/var/lib/xfi-ai/backups"))
PROJECT_ROOT = Path(os.getenv("XFI_CONNECT_PATH", "/root/XFI_CONNECT")).resolve()
SERVICE = os.getenv("XFI_CONNECT_SERVICE", "xfi-connect").strip() or "xfi-connect"
LOCK_PATH = Path(os.getenv("XFI_AI_EDIT_LOCK", "/run/lock/xfi-ai-connect-edit.lock"))

SYSTEM_PROMPT = """Ты — инженер XFI AI. Ты изменяешь установленный XFI_CONNECT непосредственно на VPS.
Сначала проанализируй структуру и запрос. Не придумывай файлы/API. Не меняй секреты.
Для плана верни JSON: {\"ready\":true/false,\"questions\":[...],\"summary\":\"...\",\"files\":[\"path\"]}.
Если данных недостаточно, ready=false и максимум 3 конкретных вопроса.
"""

PATCH_PROMPT = """Сформируй изменения для установленного XFI_CONNECT.
Верни только JSON без markdown:
{\"summary\":\"...\",\"edits\":[{\"path\":\"relative/path.py\",\"content\":\"полное новое содержимое файла\",\"reason\":\"...\"}],\"tests\":[\"...\"]}
Правила: только существующие безопасные файлы из контекста; не трогай .env, secrets, credentials, private keys, сертификаты; максимум 8 файлов; минимальные изменения; сохраняй совместимость.
"""


def _safe_path(path: str) -> bool:
    p = path.strip().replace("\\", "/")
    blocked = (".env", "secret", "credential", "private_key", "id_rsa", ".pem", ".key")
    return bool(p) and not p.startswith("/") and ".." not in p.split("/") and not any(x in p.lower() for x in blocked)


def _resolve(rel: str) -> Path:
    if not _safe_path(rel):
        raise ValueError(f"Unsafe path: {rel}")
    target = (PROJECT_ROOT / rel).resolve()
    if target != PROJECT_ROOT and PROJECT_ROOT not in target.parents:
        raise ValueError(f"Path outside project: {rel}")
    return target


def _files() -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not PROJECT_ROOT.is_dir():
        raise RuntimeError(f"XFI_CONNECT directory not found: {PROJECT_ROOT}")
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file():
            try:
                rel = path.relative_to(PROJECT_ROOT).as_posix()
            except ValueError:
                continue
            if _safe_path(rel) and path.stat().st_size <= MAX_FILE_BYTES:
                result[rel] = path
    return result


def _read(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(f"File too large: {path}")
    return raw.decode("utf-8")


def _json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError("Agent response is not an object")
    return data


async def _ask(messages: list[dict[str, str]]) -> str:
    body = json.dumps({"messages": messages, "temperature": 0.1, "max_tokens": 3000}).encode()
    response, _ = await complete(body)
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        content = choices[0].get("message", {}).get("content")
    elif isinstance(choices, dict):
        content = choices.get("message", {}).get("content")
    else:
        content = None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI returned no message content")
    return content


async def analyze_local(request: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    if not request.strip() or len(request) > MAX_REQUEST_CHARS:
        raise ValueError("Request is empty or too large")
    if history and len(history) > MAX_ANSWERS:
        raise ValueError("Too many clarification messages")
    tree = _files()
    context = "\n".join(sorted(tree)[:400])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"Установленный проект: {PROJECT_ROOT}\nФайлы:\n{context}\n\nЗапрос:\n{request}"}]
    if history:
        messages.extend(history[-MAX_ANSWERS:])
    data = _json(await _ask(messages))
    files = [str(x) for x in data.get("files", []) if str(x) in tree and _safe_path(str(x))][:MAX_FILES]
    return {"ready": bool(data.get("ready")), "questions": [str(x)[:1000] for x in data.get("questions", [])][:3], "summary": str(data.get("summary", ""))[:3000], "files": files}


async def generate_local_edits(request: str, answers: list[dict[str, str]]) -> dict[str, Any]:
    analysis = await analyze_local(request, answers)
    if not analysis["ready"]:
        raise ValueError("Requirements are not complete")
    files = _files()
    selected = [p for p in analysis["files"] if p in files]
    if not selected:
        raise ValueError("No safe existing files selected")
    context = "\n".join(f"===== {p} =====\n{_read(files[p])}" for p in selected)
    prompt = f"Запрос: {request}\nУточнения: {json.dumps(answers, ensure_ascii=False)}\nПлан: {analysis['summary']}\nКонтекст:\n{context}"
    data = _json(await _ask([{"role": "system", "content": PATCH_PROMPT}, {"role": "user", "content": prompt}]))
    edits = data.get("edits", [])
    if not isinstance(edits, list) or len(edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    safe = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise TypeError("Invalid edit entry")
        path = str(edit.get("path", ""))
        content = edit.get("content")
        if path not in selected or not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError(f"Unsafe or invalid edit: {path}")
        safe.append({"path": path, "content": content, "reason": str(edit.get("reason", ""))[:500], "expected_sha256": hashlib.sha256(_read(files[path]).encode()).hexdigest()})
    return {"summary": str(data.get("summary", analysis["summary"]))[:3000], "edits": safe, "tests": [str(x)[:500] for x in data.get("tests", [])[:10]]}


class _FileLock:
    def __enter__(self):
        import fcntl
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.fd = open(LOCK_PATH, "w", encoding="utf-8")
        try:
            fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.fd.close()
            raise RuntimeError("Another XFI_CONNECT edit is already running") from exc
        return self

    def __exit__(self, *_):
        import fcntl
        fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
        self.fd.close()


def _run(args: list[str], timeout: int) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
    return proc.returncode, proc.stdout[-12000:]


def apply_local_edits(edits: list[dict[str, str]], restart: bool = True) -> dict[str, Any]:
    if not edits or len(edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    with _FileLock():
        timestamp = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        backup_dir = BACKUP_ROOT / timestamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        changed: list[str] = []
        try:
            for edit in edits:
                target = _resolve(edit["path"])
                if not target.is_file():
                    raise ValueError(f"File no longer exists: {edit['path']}")
                current = target.read_bytes()
                if hashlib.sha256(current).hexdigest() != edit.get("expected_sha256"):
                    raise RuntimeError(f"File changed since analysis: {edit['path']}")
                backup = backup_dir / edit["path"]
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                target.write_text(edit["content"], encoding="utf-8")
                changed.append(edit["path"])
            for path in changed:
                if path.endswith(".py"):
                    py_compile.compile(str(_resolve(path)), doraise=True)
            python = shutil.which("python3") or shutil.which("python") or "python3"
            for path in changed:
                if path.endswith(".py"):
                    rc, output = _run([python, "-m", "py_compile", path], 30)
                    if rc != 0:
                        raise RuntimeError(f"py_compile failed for {path}: {output[-3000:]}")
            if restart:
                rc, output = _run(["systemctl", "restart", SERVICE], 20)
                if rc != 0:
                    raise RuntimeError(f"service restart failed: {output[-3000:]}")
                rc, state = _run(["systemctl", "is-active", SERVICE], 10)
                if rc != 0 or state.strip().splitlines()[-1:] != ["active"]:
                    raise RuntimeError(f"service is not active: {state[-3000:]}")
            return {"ok": True, "backup": str(backup_dir), "changed": changed, "service": SERVICE}
        except Exception:
            for path in reversed(changed):
                backup = backup_dir / path
                if backup.exists():
                    shutil.copy2(backup, _resolve(path))
            if restart:
                try:
                    _run(["systemctl", "restart", SERVICE], 20)
                except Exception:
                    pass
            raise


async def apply_local_edits_async(edits: list[dict[str, str]], restart: bool = True) -> dict[str, Any]:
    return await asyncio.to_thread(apply_local_edits, edits, restart)
