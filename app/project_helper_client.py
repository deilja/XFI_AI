"""Unprivileged XFI AI client for the fixed project helper."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

HELPER = os.getenv("XFI_AI_PROJECT_HELPER", "/usr/local/libexec/xfi-ai-project-helper")


def enabled() -> bool:
    return os.getenv("XFI_AI_PROJECT_HELPER_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


def call(payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError("Privileged project helper is disabled")
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )  # nosec B603 - fixed sudo/helper argv; no shell
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:] or proc.stdout[-2000:] or "Project helper failed")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Project helper returned invalid JSON") from exc
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(str(result.get("error", "Project helper failed")) if isinstance(result, dict) else "Project helper failed")
    return result
