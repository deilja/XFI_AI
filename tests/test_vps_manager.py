import pytest

import app.vps_manager as vm


def test_run_ssh_places_option_terminator_before_destination(monkeypatch, tmp_path):
    key = tmp_path / "id_ed25519"
    key.write_text("dummy")
    row = (1, "test", "127.0.0.1", 22, "root", "key", str(key))
    captured = {}

    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        return Proc()

    monkeypatch.setattr(vm.subprocess, "run", fake_run)
    rc, out = vm._run_ssh(row, "printf ok")
    assert rc == 0
    assert out == "ok"
    assert captured["args"][-3:] == ["--", "root@127.0.0.1", "printf ok"]


def test_run_ssh_rejects_empty_or_nul_remote(monkeypatch, tmp_path):
    key = tmp_path / "id_ed25519"
    key.write_text("dummy")
    row = (1, "test", "127.0.0.1", 22, "root", "key", str(key))
    monkeypatch.setattr(vm.subprocess, "run", lambda *a, **k: pytest.fail("ssh must not run"))
    with pytest.raises(ValueError):
        vm._run_ssh(row, "")
    with pytest.raises(ValueError):
        vm._run_ssh(row, "id\x00")


def test_safe_restart_allows_inactive_existing_service(monkeypatch):
    row = (1, "test", "127.0.0.1", 22, "root", "agent", "")
    calls = []

    monkeypatch.setattr(vm, "_get_vps", lambda _: row)

    def fake_run_ssh(_row, remote):
        calls.append(remote)
        return 0, "active"

    monkeypatch.setattr(vm, "_run_ssh", fake_run_ssh)
    monkeypatch.setattr(vm, "_audit", lambda *args: None)
    result = vm.safe_restart(1, "xray")
    assert result["ok"] is True
    assert calls and "systemctl cat xray" in calls[0]


def test_safe_restart_rejects_non_allowlisted_service():
    with pytest.raises(ValueError, match="not allowed"):
        vm.safe_restart(1, "xray;id")
