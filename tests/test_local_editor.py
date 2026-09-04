from pathlib import Path

import pytest

from app import local_editor


def test_safe_path_rejects_escape_and_secrets():
    assert local_editor._safe_path("bot/main.py")
    assert not local_editor._safe_path("../outside.py")
    assert not local_editor._safe_path(".env")
    assert not local_editor._safe_path("certs/server.pem")


def test_resolve_stays_inside_project(monkeypatch, tmp_path):
    monkeypatch.setattr(local_editor, "PROJECT_ROOT", tmp_path.resolve())
    assert local_editor._resolve("bot/main.py") == (tmp_path / "bot/main.py").resolve()
    with pytest.raises(ValueError):
        local_editor._resolve("../outside.py")


def test_apply_local_edits_creates_backup_and_does_not_need_github(monkeypatch, tmp_path):
    project = tmp_path / "XFI_CONNECT"
    project.mkdir()
    target = project / "main.py"
    target.write_text("print('old')\n", encoding="utf-8")
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(local_editor, "PROJECT_ROOT", project.resolve())
    monkeypatch.setattr(local_editor, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(local_editor, "LOCK_PATH", tmp_path / "edit.lock")

    import hashlib
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    result = local_editor.apply_local_edits(
        [{"path": "main.py", "content": "print('new')\n", "reason": "test", "expected_sha256": expected}],
        restart=False,
    )

    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "print('new')\n"
    assert (Path(result["backup"]) / "main.py").read_text(encoding="utf-8") == "print('old')\n"


def test_apply_refuses_stale_file(monkeypatch, tmp_path):
    project = tmp_path / "XFI_CONNECT"
    project.mkdir()
    target = project / "main.py"
    target.write_text("print('current')\n", encoding="utf-8")
    monkeypatch.setattr(local_editor, "PROJECT_ROOT", project.resolve())
    monkeypatch.setattr(local_editor, "BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(local_editor, "LOCK_PATH", tmp_path / "edit.lock")

    with pytest.raises(RuntimeError, match="changed since analysis"):
        local_editor.apply_local_edits(
            [{"path": "main.py", "content": "print('new')\n", "reason": "test", "expected_sha256": "0" * 64}],
            restart=False,
        )
    assert target.read_text(encoding="utf-8") == "print('current')\n"
