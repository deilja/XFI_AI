from pathlib import Path

import pytest

from deploy import xfi_ai_project_helper as helper


def test_safe_rel_rejects_traversal_and_secrets():
    for value in ("../x", "/etc/passwd", ".env", "config/secret.json", "tls/server.key"):
        with pytest.raises(ValueError):
            helper.safe_rel(value)


def test_target_rejects_symlink_escape(tmp_path: Path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "x.txt").write_text("x", encoding="utf-8")
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        helper.target(root, "link/x.txt")


def test_project_allowlist_has_only_expected_services():
    assert {item["service"] for item in helper.PROJECTS.values()} == {"xfi-connect", "xfi-3xui-webapp"}


def test_helper_has_no_shell_command_interface():
    source = Path(helper.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "os.system(" not in source
    assert "eval(" not in source


def test_cfg_rejects_non_local_health(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(helper.PROJECTS["connect"], "path", tmp_path)
    monkeypatch.setenv("XFI_CONNECT_HEALTH_URL", "http://example.com/health")
    with pytest.raises(ValueError, match="localhost"):
        helper.cfg("connect")
