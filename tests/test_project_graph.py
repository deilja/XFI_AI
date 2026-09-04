from pathlib import Path

from app.project_graph import build_graph, graph_context


def test_graph_resolves_python_and_typescript_local_imports(tmp_path: Path):
    (tmp_path / "app.py").write_text("from services import api\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("import { api } from './api';\n", encoding="utf-8")
    (tmp_path / "src" / "api.ts").write_text("export const api = 1;\n", encoding="utf-8")

    graph = build_graph(tmp_path)

    assert graph["node_count"] == 4
    assert {edge["target"] for edge in graph["edges"]} == {"services/api.py", "src/api.ts"}
    assert "node_count" in graph_context(graph)


def test_graph_excludes_secret_like_paths(tmp_path: Path):
    (tmp_path / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (tmp_path / "secret_config.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "safe.py").write_text("x = 1\n", encoding="utf-8")

    graph = build_graph(tmp_path)

    assert [node["path"] for node in graph["nodes"]] == ["safe.py"]
