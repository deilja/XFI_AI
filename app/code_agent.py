"""Guarded natural-language coding agent for the XFI Telegram bot."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .providers import complete

MAX_FILE_BYTES = 120_000
MAX_FILES = 8
MAX_REQUEST_CHARS = 8_000
MAX_ANSWERS = 12
CI_TIMEOUT_SECONDS = 300
CI_POLL_SECONDS = 10

SYSTEM_PROMPT = """Ты — инженер XFI AI. Ты помогаешь изменять код Telegram-бота XFI_CONNECT по простому запросу на русском.
Работай осторожно: не придумывай файлы и API. Сначала выясни недостающие требования.
После получения достаточных ответов подготовь минимальный набор изменений.
Для плана верни JSON: {\"ready\":true/false,\"questions\":[...],\"summary\":\"...\",\"files\":[\"path\"]}.
Если данных недостаточно, ready=false и задай максимум 3 конкретных вопроса.
Для готового плана изменения пока НЕ генерируй код.
"""

PATCH_PROMPT = """Сформируй изменения для репозитория XFI_CONNECT.
Верни только JSON без markdown:
{\"summary\":\"...\",\"edits\":[{\"path\":\"relative/path.py\",\"content\":\"полное новое содержимое файла\",\"reason\":\"...\"}],\"tests\":[\"...\"]}
Правила: редактируй только существующие файлы из контекста; не трогай секреты, .env, ключи, сертификаты и произвольные системные файлы; максимум 8 файлов; минимальные изменения; сохраняй совместимость с текущим кодом.
"""


@dataclass
class AgentResult:
    ready: bool
    questions: list[str]
    summary: str
    files: list[str]


@dataclass
class CIResult:
    state: str
    summary: str
    checks: list[str]


def _repo() -> str:
    return os.getenv("XFI_AI_CODE_REPO", "deilja/XFI_CONNECT").strip()


def _token() -> str:
    return os.getenv("XFI_AI_GITHUB_TOKEN", "").strip()


def _headers() -> dict[str, str]:
    token = _token()
    if not token:
        raise RuntimeError("XFI_AI_GITHUB_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _safe_path(path: str) -> bool:
    p = path.strip().replace("\\", "/")
    blocked = (".env", "secret", "credential", "private_key", "id_rsa")
    return (
        bool(p)
        and not p.startswith("/")
        and ".." not in p.split("/")
        and not any(x in p.lower() for x in blocked)
    )


async def _github_get(path: str) -> Any:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"https://api.github.com{path}", headers=_headers())
    response.raise_for_status()
    return response.json()


async def _repo_tree() -> dict[str, str]:
    data = await _github_get(f"/repos/{_repo()}/git/trees/HEAD?recursive=1")
    files: dict[str, str] = {}
    for item in data.get("tree", []):
        if item.get("type") == "blob" and item.get("path") and _safe_path(item["path"]):
            files[item["path"]] = item.get("sha", "")
    return files


async def _file(path: str, ref: str = "HEAD") -> str:
    encoded = quote(path, safe="/")
    data = await _github_get(f"/repos/{_repo()}/contents/{encoded}?ref={quote(ref, safe='')}")
    raw = base64.b64decode(data["content"].replace("\n", ""))
    if len(raw) > MAX_FILE_BYTES:
        raise RuntimeError(f"File too large: {path}")
    return raw.decode("utf-8")


async def _ask_model(messages: list[dict[str, str]]) -> str:
    body = json.dumps({"messages": messages, "temperature": 0.1, "max_tokens": 3000}).encode()
    response, _ = await complete(body)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    data = json.loads(text)
    if not isinstance(data, dict):
        raise TypeError("Agent response is not an object")
    return data


async def analyze_request(request: str, history: list[dict[str, str]] | None = None) -> AgentResult:
    if not request.strip() or len(request) > MAX_REQUEST_CHARS:
        raise ValueError("Request is empty or too large")
    if history and len(history) > MAX_ANSWERS:
        raise ValueError("Too many clarification messages")
    tree = await _repo_tree()
    context = "\n".join(sorted(tree)[:400])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Репозиторий: {_repo()}\nФайлы:\n{context}\n\nЗапрос:\n{request}",
        },
    ]
    if history:
        messages.extend(history[-MAX_ANSWERS:])
    data = _json(await _ask_model(messages))
    questions = [str(x)[:1000] for x in data.get("questions", [])][:3]
    files = [str(x) for x in data.get("files", []) if _safe_path(str(x))][:MAX_FILES]
    return AgentResult(
        bool(data.get("ready")),
        questions,
        str(data.get("summary", ""))[:3000],
        files,
    )


async def generate_edits(request: str, answers: list[dict[str, str]]) -> dict[str, Any]:
    if len(answers) > MAX_ANSWERS:
        raise ValueError("Too many clarification messages")
    tree = await _repo_tree()
    analysis = await analyze_request(request, answers)
    if not analysis.ready:
        raise ValueError("Requirements are not complete")
    files = [p for p in analysis.files if p in tree]
    if not files:
        raise ValueError("No safe existing files selected")
    contents = []
    for path in files:
        contents.append(f"===== {path} =====\n{await _file(path)}")
    context = "\n".join(contents)
    prompt = (
        f"Запрос пользователя: {request}\n"
        f"Уточнения: {json.dumps(answers, ensure_ascii=False)}\n"
        f"План: {analysis.summary}\nКонтекст:\n{context}"
    )
    data = _json(
        await _ask_model(
            [{"role": "system", "content": PATCH_PROMPT}, {"role": "user", "content": prompt}]
        )
    )
    edits = data.get("edits", [])
    if not isinstance(edits, list) or len(edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    safe = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise TypeError("Invalid edit entry")
        path = str(edit.get("path", ""))
        content = edit.get("content")
        if path not in files or not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError(f"Unsafe or invalid edit: {path}")
        safe.append(
            {
                "path": path,
                "content": content,
                "reason": str(edit.get("reason", ""))[:500],
                # Bind the generated patch to the exact repository version that
                # was reviewed, preventing a stale agent result from overwriting
                # a newer upstream change.
                "expected_sha": tree[path],
            }
        )
    return {
        "summary": str(data.get("summary", analysis.summary))[:3000],
        "edits": safe,
        "tests": [str(x)[:500] for x in data.get("tests", [])[:10]],
    }


async def create_branch_and_commit(edits: list[dict[str, str]], message: str) -> tuple[str, str, str]:
    repo = _repo()
    headers = _headers()
    branch = f"xfi-ai/{int(time.time())}-{secrets.token_hex(4)}"
    async with httpx.AsyncClient(timeout=30) as client:
        ref = await client.get(
            f"https://api.github.com/repos/{repo}/git/ref/heads/main",
            headers=headers,
        )
        ref.raise_for_status()
        main_sha = ref.json()["object"]["sha"]

        # Refuse to create a patch if any source file changed after the agent
        # inspected it. This avoids lost updates and makes confirmation meaningful.
        for edit in edits:
            expected_sha = edit.get("expected_sha")
            if not expected_sha:
                raise ValueError(f"Missing source revision for {edit.get('path', '')}")
            current = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{quote(edit['path'], safe='/')}",
                headers=headers,
                params={"ref": "main"},
            )
            current.raise_for_status()
            if current.json().get("sha") != expected_sha:
                raise ValueError(f"Source file changed since analysis: {edit['path']}")

        create = await client.post(
            f"https://api.github.com/repos/{repo}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch}", "sha": main_sha},
        )
        create.raise_for_status()
        for edit in edits:
            current = await client.get(
                f"https://api.github.com/repos/{repo}/contents/{quote(edit['path'], safe='/')}",
                headers=headers,
                params={"ref": branch},
            )
            current.raise_for_status()
            payload = {
                "message": message[:120],
                "content": base64.b64encode(edit["content"].encode()).decode(),
                "sha": current.json()["sha"],
                "branch": branch,
            }
            updated = await client.put(
                f"https://api.github.com/repos/{repo}/contents/{quote(edit['path'], safe='/')}",
                headers=headers,
                json=payload,
            )
            updated.raise_for_status()
        pr = await client.post(
            f"https://api.github.com/repos/{repo}/pulls",
            headers=headers,
            json={
                "title": message[:120],
                "head": branch,
                "base": "main",
                "body": "Изменения подготовлены XFI AI по подтверждённому запросу администратора.\n\nCI должен проверить ветку автоматически. Слияние в main выполняется отдельно.",
                "draft": False,
            },
        )
        pr.raise_for_status()
        pr_url = pr.json().get("html_url", "")
    return branch, f"https://github.com/{repo}/tree/{branch}", pr_url


async def wait_for_ci(branch: str, timeout: int = CI_TIMEOUT_SECONDS, poll: int = CI_POLL_SECONDS) -> CIResult:
    """Wait for GitHub Checks on the branch head and return a compact result."""
    repo = _repo()
    headers = _headers()
    deadline = time.monotonic() + max(30, min(timeout, 900))
    async with httpx.AsyncClient(timeout=20) as client:
        head_sha = ""
        while time.monotonic() < deadline:
            pr_response = await client.get(
                f"https://api.github.com/repos/{repo}/pulls",
                headers=headers,
                params={"head": f"{repo.split('/', 1)[0]}:{branch}", "state": "open", "per_page": 10},
            )
            pr_response.raise_for_status()
            prs = pr_response.json()
            if prs:
                head_sha = prs[0].get("head", {}).get("sha", "")
            if head_sha:
                checks = await client.get(
                    f"https://api.github.com/repos/{repo}/commits/{head_sha}/check-runs",
                    headers=headers,
                    params={"per_page": 50},
                )
                checks.raise_for_status()
                items = checks.json().get("check_runs", [])
                if items:
                    names = []
                    pending = False
                    failed = False
                    for item in items:
                        name = str(item.get("name", "check"))
                        status = str(item.get("status", ""))
                        conclusion = str(item.get("conclusion", ""))
                        names.append(f"{name}: {conclusion or status}")
                        if status != "completed":
                            pending = True
                        elif conclusion not in {"success", "neutral", "skipped"}:
                            failed = True
                    if not pending:
                        state = "fail" if failed else "pass"
                        return CIResult(state, "GitHub Checks завершены.", names[:20])
            await asyncio.sleep(poll)
    return CIResult("timeout", "GitHub Checks не завершились за отведённое время.", [])
