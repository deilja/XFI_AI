"""Lightweight architecture graph for the XFI project code agent."""
from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_GRAPH_FILES = 500
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".cache", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".turbo", "coverage"}
BLOCKED_PARTS = (".env", "secret", "credential", "private_key", "id_rsa", ".pem", ".key")


@dataclass(frozen=True)
class Node:
    path: str
    kind: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str


def _safe(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return bool(path) and not path.startswith("/") and ".." not in parts and not any(part.lower() in BLOCKED_PARTS or any(blocked in part.lower() for blocked in BLOCKED_PARTS) for part in parts)


def _python_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append("." * node.level + node.module)
    return result


def _ts_imports(text: str) -> list[str]:
    return re.findall(r"(?:from\s+|import\s*\(?\s*)[\"']([^\"']+)[\"']", text)


def _kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return "typescript"
    if Path(path).name in {"package.json", "pyproject.toml", "bun.lock", "bun.lockb"}:
        return "config"
    return "other"


def _resolve_import(source: str, imported: str, known: set[str], kind: str) -> str | None:
    if kind == "python":
        module = imported.lstrip(".")
        base = Path(source).parent if imported.startswith(".") else Path(".")
        candidate = base.joinpath(*module.split(".")) if module else base
        options = [candidate.with_suffix(".py"), candidate / "__init__.py"]
        if not imported.startswith("."):
            options.extend([Path(module.replace(".", "/") + ".py"), Path(module.replace(".", "/")) / "__init__.py"])
        return next((p.as_posix() for p in options if p.as_posix() in known), None)
    if imported.startswith("."):
        base = Path(source).parent / imported
        options = [base, *[Path(f"{base}{suffix}") for suffix in (".ts", ".tsx", ".js", ".jsx")], base / "index.ts", base / "index.tsx"]
        return next((p.as_posix() for p in options if p.as_posix() in known), None)
    return None


def build_graph(root: Path, limit: int = MAX_GRAPH_FILES) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f"Project directory not found: {root}")
    paths: dict[str, Path] = {}
    for base, dirs, filenames in os.walk(root, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(base) / filename
            try:
                rel = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            if _safe(rel) and len(paths) < limit:
                paths[rel] = path
    known = set(paths)
    nodes = [Node(path, _kind(path)) for path in sorted(paths)]
    edges: list[Edge] = []
    for source, path in paths.items():
        kind = _kind(source)
        if kind not in {"python", "typescript"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        imports = _python_imports(text) if kind == "python" else _ts_imports(text)
        for imported in imports:
            target = _resolve_import(source, imported, known, kind)
            if target and target != source:
                edges.append(Edge(source, target, "import"))
    return {"nodes": [asdict(node) for node in nodes], "edges": [asdict(edge) for edge in edges], "node_count": len(nodes), "edge_count": len(edges)}


def graph_context(graph: dict[str, Any]) -> str:
    return json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
