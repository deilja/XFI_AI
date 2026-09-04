"""Append-only audit log for XFI AI project control operations."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

AUDIT_PATH = Path(os.getenv("XFI_AI_PROJECT_AUDIT", "/var/lib/xfi-ai/project-audit.jsonl"))


def record(action: str, project: str, **details: object) -> None:
    event = {"ts": int(time.time()), "action": action, "project": project, **details}
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def recent(limit: int = 200) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    limit = max(1, min(limit, 1000))
    lines = AUDIT_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    result = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
        except json.JSONDecodeError:
            continue
    return result
