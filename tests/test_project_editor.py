import hashlib

import pytest

from app import project_editor


def test_projects_are_independent():
    assert project_editor.PROJECTS["connect"]["name"] == "XFI_CONNECT"
    assert project_editor.PROJECTS["webapp"]["name"] == "XFI_3XUI_WebApp"
    assert project_editor.PROJECTS["connect"]["default_path"] != project_editor.PROJECTS["webapp"]["default_path"]


def test_safe_path_rejects_escape_and_secrets():
    assert project_editor.safe_path("src/index.ts")
    assert not project_editor.safe_path("../outside.ts")
    assert not project_editor.safe_path(".env")
    assert not project_editor.safe_path("certs/server.pem")


def test_apply_webapp_directly(monkeypatch, tmp_path):
    project = tmp_path / "webapp"
    project.mkdir()
    target = project / "src.ts"
    target.write_text("const old = 1;\n", encoding="utf-8")
    cfg = project_editor.project_config("webapp")
    cfg["path"] = str(project)
    monkeypatch.setitem(project_editor.PROJECTS, "webapp", {**project_editor.PROJECTS["webapp"], "default_path": str(project)})
    monkeypatch.setattr(project_editor, "shutil", project_editor.shutil)
    monkeypatch.setattr(project_editor, "_validate", lambda cfg, changed: None)
    monkeypatch.setenv("XFI_AI_BACKUP_DIR", str(tmp_path / "backups"))
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    result = project_editor.apply_edits("webapp", [{"path": "src.ts", "content": "const old = 2;\n", "reason": "test", "expected_sha256": expected}], restart=False)
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "const old = 2;\n"
    assert (tmp_path / "backups" / "webapp" / next((p.name for p in (tmp_path / "backups" / "webapp").iterdir())) / "src.ts").read_text(encoding="utf-8") == "const old = 1;\n"


def test_apply_refuses_stale_file(monkeypatch, tmp_path):
    project = tmp_path / "webapp"
    project.mkdir()
    target = project / "src.ts"
    target.write_text("const current = true;\n", encoding="utf-8")
    monkeypatch.setitem(project_editor.PROJECTS, "webapp", {**project_editor.PROJECTS["webapp"], "default_path": str(project)})
    monkeypatch.setenv("XFI_AI_BACKUP_DIR", str(tmp_path / "backups"))
    with pytest.raises(RuntimeError, match="changed since analysis"):
        project_editor.apply_edits("webapp", [{"path": "src.ts", "content": "const changed = true;\n", "reason": "test", "expected_sha256": "0" * 64}], restart=False)
    assert target.read_text(encoding="utf-8") == "const current = true;\n"
