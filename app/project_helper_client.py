"""Unprivileged client for the fixed XFI AI project helper."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

HELPER = os.getenv("XFI_AI_PROJECT_HELPER", "/usr/local/libexec/xfi-ai-project-helper")


def enabled() -> bool:
    return (
        os.getenv("XFI_AI_PROJECT_HELPER_ENABLED", "1").strip().lower()
        in {"1", "true", "yes", "on"}
        and os.path.isfile(HELPER)
        and os.access(HELPER, os.X_OK)
    )


def call(payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError("Privileged project helper is not installed or disabled")
    project = str(payload.get("project", "")).strip().lower()
    if project not in {"connect", "webapp"}:
        raise ValueError("Unknown project")
    action = str(payload.get("action", "")).strip().lower()
    if action not in {"read", "apply", "restart", "health"}:
        raise ValueError("Unsupported helper action")
    proc = subprocess.run(
        ["sudo", "-n", HELPER],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )  # nosec B603 - fixed sudo/helper argv; no shell
    if proc.returncode != 0:
        detail = proc.stdout.strip() or proc.stderr.strip() or "Project helper failed"
        try:
            data = json.loads(detail)
            raise RuntimeError(str(data.get("error", detail)))
        except json.JSONDecodeError:
            raise RuntimeError(detail[-2000:]) from None
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Project helper returned invalid JSON") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(
            str(result.get("error", "Project helper failed"))
            if isinstance(result, dict)
            else "Project helper failed"
        )
    return result


def read(project: str, path: str) -> str:
    return str(call({"action": "read", "project": project, "path": path})["content"])


def apply(project: str, edits: list[dict[str, Any]], restart: bool = True) -> dict[str, Any]:
    return call({"action": "apply", "project": project, "edits": edits, "restart": restart}, timeout=180)


def restart(project: str) -> dict[str, Any]:
    return call({"action": "restart", "project": project}, timeout=60)


def health(project: str) -> dict[str, Any]:
    return call({"action": "health", "project": project}, timeout=30)
