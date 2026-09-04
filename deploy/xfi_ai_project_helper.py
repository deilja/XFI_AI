#!/usr/bin/env python3
"""Root-owned, allowlisted helper for XFI AI project edits."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

MAX_FILE_BYTES = 120_000
MAX_FILES = 8
BLOCKED = (".env", "secret", "credential", "private_key", "id_rsa", ".pem", ".key")
PROJECTS = {
    "connect": {"path": Path("/root/XFI_CONNECT"), "service": "xfi-connect", "health_env": "XFI_CONNECT_HEALTH_URL", "default_health": ""},
    "webapp": {"path": Path("/opt/XFI_3XUI_WebApp"), "service": "xfi-3xui-webapp", "health_env": "XFI_3XUI_WEBAPP_HEALTH_URL", "default_health": "http://127.0.0.1:3000/health"},
}
BACKUP_ROOT = Path("/var/lib/xfi-ai/backups")


def fail(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), flush=True)
    raise SystemExit(code)


def cfg(project: str) -> dict[str, object]:
    if project not in PROJECTS:
        raise ValueError("Unknown project")
    item = PROJECTS[project]
    root = item["path"].resolve()
    if not root.is_dir():
        raise RuntimeError(f"Project directory not found: {root}")
    health = os.getenv(str(item["health_env"]), str(item["default_health"])).strip()
    if health:
        parsed = urlparse(health)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Health URL must point to localhost")
    return {"path": root, "service": str(item["service"]), "health": health}


def safe_rel(value: object) -> str:
    rel = str(value or "").strip().replace("\\", "/")
    parts = rel.split("/")
    if not rel or rel.startswith("/") or ".." in parts or any(any(b in p.lower() for b in BLOCKED) for p in parts):
        raise ValueError(f"Unsafe path: {rel}")
    return rel


def target(root: Path, rel: object) -> Path:
    path = (root / safe_rel(rel)).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Path outside project")
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_health(url: str) -> None:
    if not url:
        return
    with urlopen(url, timeout=10) as response:  # nosec B310 - URL is validated as localhost above
        if response.status < 200 or response.status >= 400:
            raise RuntimeError(f"health returned HTTP {response.status}")


def validate(root: Path, project: str, changed: list[str]) -> None:
    if project == "connect":
        for rel in changed:
            if rel.endswith(".py"):
                subprocess.run(["python3", "-m", "py_compile", rel], cwd=root, check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)  # nosec B603
    else:
        subprocess.run(["bun", "run", "typecheck"], cwd=root, check=True, timeout=90, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # nosec B603


def restart(service: str) -> None:
    subprocess.run(["systemctl", "restart", service], check=True, timeout=30, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # nosec B603
    result = subprocess.run(["systemctl", "is-active", service], check=False, timeout=10, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)  # nosec B603
    if result.returncode != 0 or result.stdout.strip() != "active":
        raise RuntimeError(f"service is not active: {result.stdout[-1000:]}")


def apply(project: str, request: dict[str, object]) -> dict[str, object]:
    item = cfg(project)
    root = item["path"]  # type: ignore[assignment]
    service = item["service"]  # type: ignore[assignment]
    edits = request.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > MAX_FILES:
        raise ValueError("Invalid edit set")
    restart_requested = bool(request.get("restart", True))
    lock = Path("/run/lock") / f"xfi-ai-{project}-edit.lock"
    lock.parent.mkdir(mode=0o755, exist_ok=True)
    changed: list[str] = []
    backup_dir = BACKUP_ROOT / project / (time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(3).hex())
    tmp_files: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    with lock.open("w", encoding="utf-8") as lock_fd:
        import fcntl
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another project edit is running") from exc
        backup_dir.mkdir(mode=0o750, parents=True, exist_ok=False)
        try:
            for edit in edits:
                if not isinstance(edit, dict):
                    raise ValueError("Invalid edit entry")
                rel = safe_rel(edit.get("path"))
                path = target(root, rel)
                content = edit.get("content")
                expected = str(edit.get("expected_sha256", ""))
                if not path.is_file() or not isinstance(content, str):
                    raise ValueError(f"Invalid file: {rel}")
                if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                    raise ValueError(f"File too large: {rel}")
                if sha(path) != expected:
                    raise RuntimeError(f"File changed since analysis: {rel}")
                backup = backup_dir / rel
                backup.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                backups.append((path, backup))
                fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.xfi-ai-", dir=path.parent)
                tmp = Path(tmp_name)
                tmp_files.append(tmp)
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    out.write(content)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp, path)
                tmp_files.remove(tmp)
                changed.append(rel)
            validate(root, project, changed)
            if restart_requested:
                restart(service)
                validate_health(str(item["health"]))
            return {"ok": True, "project": project, "changed": changed, "backup": str(backup_dir), "service": service, "restarted": restart_requested}
        except Exception:
            for tmp in tmp_files:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            for path, backup in reversed(backups):
                try:
                    os.replace(backup, path)
                except OSError:
                    try:
                        shutil.copy2(backup, path)
                    except OSError:
                        pass
            if restart_requested:
                try:
                    restart(service)
                except Exception:
                    pass
            raise


def main() -> None:
    if os.geteuid() != 0:
        fail("helper must run as root")
    try:
        request = json.load(__import__("sys").stdin)
        if not isinstance(request, dict):
            raise ValueError("JSON object required")
        action = str(request.get("action", ""))
        project = str(request.get("project", "")).strip().lower()
        item = cfg(project)
        if action == "read":
            path = target(item["path"], request.get("path"))  # type: ignore[arg-type]
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Invalid or oversized file")
            print(json.dumps({"ok": True, "path": safe_rel(request.get("path")), "content": path.read_text(encoding="utf-8")}, ensure_ascii=False))
        elif action == "apply":
            print(json.dumps(apply(project, request), ensure_ascii=False))
        elif action == "restart":
            restart(item["service"])  # type: ignore[arg-type]
            validate_health(str(item["health"]))
            print(json.dumps({"ok": True, "project": project, "restarted": True}, ensure_ascii=False))
        elif action == "health":
            validate_health(str(item["health"]))
            print(json.dumps({"ok": True, "project": project, "health": "ok"}, ensure_ascii=False))
        else:
            raise ValueError("Unsupported action")
    except Exception as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
