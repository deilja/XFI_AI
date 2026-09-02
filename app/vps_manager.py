import os
import re
import sqlite3
import subprocess  # nosec B404 - subprocess is required for fixed-argument SSH execution
import time
from pathlib import Path

DB_PATH = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))
ALLOWED_SERVICES = {"x-ui", "3x-ui", "xray", "nginx", "docker"}
AUTH_TYPES = {"key", "agent"}
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]{0,252}$")


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS vps (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        host TEXT NOT NULL UNIQUE,
        port INTEGER NOT NULL DEFAULT 22,
        username TEXT NOT NULL DEFAULT 'root',
        auth_type TEXT NOT NULL DEFAULT 'key',
        auth_value TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_check REAL,
        last_ok INTEGER DEFAULT 0,
        last_error TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        action TEXT NOT NULL,
        target TEXT NOT NULL,
        result TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def add_vps(name: str, host: str, port: int = 22, username: str = "root", auth_type: str = "key", auth_value: str = ""):
    if auth_type not in AUTH_TYPES:
        raise ValueError("auth_type must be key or agent; password authentication is disabled")
    host = host.strip()
    username = username.strip()
    if not host or not _HOST_RE.fullmatch(host):
        raise ValueError("invalid VPS host")
    if not username or len(username) > 100 or any(c.isspace() for c in username) or username.startswith("-"):
        raise ValueError("invalid SSH username")
    if not (1 <= int(port) <= 65535):
        raise ValueError("invalid SSH port")
    if auth_type == "key":
        key_path = Path(auth_value).expanduser()
        if not key_path.is_absolute():
            raise ValueError("SSH key path must be absolute")
        if len(str(key_path)) > 500:
            raise ValueError("SSH key path is too long")
        stored = str(key_path)
    else:
        stored = ""
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO vps(name,host,port,username,auth_type,auth_value) VALUES(?,?,?,?,?,?)",
            (name[:100], host, int(port), username, auth_type, stored),
        )
        vid = cur.lastrowid
    return vid


def list_vps():
    with _db() as conn:
        rows = conn.execute("SELECT id,name,host,port,username,auth_type,created_at,last_check,last_ok,last_error FROM vps ORDER BY id DESC").fetchall()
    fields = ("id", "name", "host", "port", "username", "auth_type", "created_at", "last_check", "last_ok", "last_error")
    return [dict(zip(fields, row)) for row in rows]


def delete_vps(vps_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM vps WHERE id=?", (vps_id,))
        conn.commit()


def _get_vps(vps_id: int):
    with _db() as conn:
        row = conn.execute("SELECT id,name,host,port,username,auth_type,auth_value FROM vps WHERE id=?", (vps_id,)).fetchone()
    if not row:
        raise KeyError("VPS not found")
    return row


def _ssh_base(row):
    _, _, host, port, username, auth_type, auth_value = row
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new", "-p", str(port)]
    if auth_type == "key":
        if not auth_value:
            raise ValueError("SSH key path is missing")
        key = Path(auth_value).expanduser()
        if not key.is_absolute() or not key.is_file():
            raise FileNotFoundError(f"SSH key not found: {key}")
        args += ["-i", str(key)]
    elif auth_type != "agent":
        raise ValueError("unsupported SSH authentication type")
    args.append(f"{username}@{host}")
    return args


def _run_ssh(row, remote: str):
    args = _ssh_base(row)
    if not remote or len(remote) > 12000:
        raise ValueError("remote command is empty or too long")
    proc = subprocess.run(  # nosec B603 - shell=False; executable and arguments are constructed from validated inputs
        args + [remote], capture_output=True, text=True, timeout=20, check=False, env=os.environ.copy()
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()[-8000:]


def _audit(action: str, target: str, result: str):
    with _db() as conn:
        conn.execute("INSERT INTO audit_log(action,target,result) VALUES(?,?,?)", (action[:100], target[:255], result[:2000]))
        conn.commit()


def audit(limit: int = 100):
    with _db() as conn:
        rows = conn.execute("SELECT id,created_at,action,target,result FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
    return [dict(zip(("id", "created_at", "action", "target", "result"), row)) for row in rows]


def detect(vps_id: int):
    row = _get_vps(vps_id)
    probe = r'''printf '__XFI__\n'; printf 'hostname='; hostname 2>/dev/null; printf '\nos='; . /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME"; printf '\n'; printf 'xui='; systemctl list-unit-files 2>/dev/null | grep -E '^(x-ui|3x-ui)\.service' | tr '\n' ','; printf '\nxray='; systemctl list-unit-files 2>/dev/null | grep '^xray\.service' | tr '\n' ','; printf '\nnginx='; systemctl list-unit-files 2>/dev/null | grep '^nginx\.service' | tr '\n' ','; printf '\ndocker='; command -v docker >/dev/null 2>&1 && printf 'installed' || printf 'absent'; printf '\nyadrenovpn='; pgrep -af 'YadrenoVPN|yadrenovpn' 2>/dev/null | head -3 | tr '\n' ';'; printf '\nopenclaw='; command -v openclaw >/dev/null 2>&1 && printf 'installed' || printf 'absent'; printf '\nopenclaw_gateway='; systemctl --user is-active openclaw-gateway 2>/dev/null || true; printf '\n'''
    try:
        rc, out = _run_ssh(row, probe)
        ok = rc == 0 and "__XFI__" in out
        with _db() as conn:
            conn.execute("UPDATE vps SET last_check=?,last_ok=?,last_error=? WHERE id=?", (time.time(), int(ok), "" if ok else out[-1000:], vps_id))
            conn.commit()
        _audit("detect", row[2], "ok" if ok else out[-1000:])
        return {"ok": ok, "raw": out}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        with _db() as conn:
            conn.execute("UPDATE vps SET last_check=?,last_ok=0,last_error=? WHERE id=?", (time.time(), str(exc)[:1000], vps_id))
            conn.commit()
        _audit("detect", row[2], str(exc))
        return {"ok": False, "error": str(exc)}


def safe_restart(vps_id: int, service: str):
    if service not in ALLOWED_SERVICES:
        raise ValueError("Service is not allowed")
    row = _get_vps(vps_id)
    remote = f"systemctl cat {service} >/dev/null 2>&1 || exit 3; systemctl restart {service} || exit 5; systemctl is-active {service}"
    rc, out = _run_ssh(row, remote)
    ok = rc == 0 and out.splitlines()[-1:] == ["active"]
    _audit("restart", f"{row[2]}:{service}", "ok" if ok else out[-1000:])
    return {"ok": ok, "service": service, "status": out}
