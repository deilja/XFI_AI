import base64
import hashlib
import hmac
import os
import secrets
import shlex
import sqlite3
import subprocess
import time
from pathlib import Path

DB_PATH = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))
SECRET = os.getenv("XFI_AI_VPS_SECRET") or os.getenv("XFI_AI_KEY_PEPPER") or ""


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS vps (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL UNIQUE,
        port INTEGER NOT NULL DEFAULT 22, username TEXT NOT NULL DEFAULT 'root',
        auth_type TEXT NOT NULL DEFAULT 'key', auth_value TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_check REAL, last_ok INTEGER DEFAULT 0, last_error TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        action TEXT NOT NULL, target TEXT NOT NULL, result TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _crypt(value: str) -> str:
    if not value or not SECRET:
        return ""
    key = hashlib.sha256(SECRET.encode()).digest()
    raw = value.encode()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return base64.urlsafe_b64encode(out).decode()


def _decrypt(value: str) -> str:
    if not value or not SECRET:
        return ""
    try:
        key = hashlib.sha256(SECRET.encode()).digest()
        raw = base64.urlsafe_b64decode(value.encode())
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode()
    except Exception:
        return ""


def add_vps(name: str, host: str, port: int, username: str, auth_type: str, auth_value: str = ""):
    if auth_type not in {"key", "password", "agent"}:
        raise ValueError("auth_type must be key, password or agent")
    if not (1 <= port <= 65535):
        raise ValueError("invalid SSH port")
    if auth_type == "password" and not SECRET:
        raise ValueError("XFI_AI_VPS_SECRET is required for password authentication")
    stored = _crypt(auth_value) if auth_type == "password" else auth_value[:500]
    with _db() as conn:
        cur = conn.execute("INSERT INTO vps(name,host,port,username,auth_type,auth_value) VALUES(?,?,?,?,?,?)", (name[:100], host[:255], port, username[:100], auth_type, stored))
        vid = cur.lastrowid
    return vid


def list_vps():
    with _db() as conn:
        rows = conn.execute("SELECT id,name,host,port,username,auth_type,created_at,last_check,last_ok,last_error FROM vps ORDER BY id DESC").fetchall()
    fields = ("id","name","host","port","username","auth_type","created_at","last_check","last_ok","last_error")
    return [dict(zip(fields, row)) for row in rows]


def delete_vps(vps_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM vps WHERE id=?", (vps_id,))
        conn.commit()


def _ssh_base(row):
    host, port, username, auth_type, auth_value = row[2], row[3], row[4], row[5], row[6]
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new", "-p", str(port)]
    if auth_type == "key" and auth_value:
        args += ["-i", auth_value]
    args.append(f"{username}@{host}")
    return args, auth_type, _decrypt(auth_value)


def _run_ssh(row, remote: str):
    args, auth_type, password = _ssh_base(row)
    if auth_type == "password":
        raise RuntimeError("Password SSH is stored for metadata but execution requires an SSH agent/key; use auth_type=key or agent")
    p = subprocess.run(args + ["--", remote], capture_output=True, text=True, timeout=15, check=False)
    return p.returncode, (p.stdout + p.stderr).strip()[-8000:]


def _audit(action: str, target: str, result: str):
    with _db() as conn:
        conn.execute("INSERT INTO audit_log(action,target,result) VALUES(?,?,?)", (action, target[:255], result[:2000]))
        conn.commit()


def audit(limit: int = 100):
    with _db() as conn:
        rows = conn.execute("SELECT id,created_at,action,target,result FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
    return [dict(zip(("id","created_at","action","target","result"), row)) for row in rows]


def detect(vps_id: int):
    with _db() as conn:
        row = conn.execute("SELECT id,name,host,port,username,auth_type,auth_value FROM vps WHERE id=?", (vps_id,)).fetchone()
    if not row:
        raise KeyError("VPS not found")
    probe = r'''printf '__XFI__\n'; printf 'hostname='; hostname 2>/dev/null; printf '\nos='; . /etc/os-release 2>/dev/null && printf '%s' "$PRETTY_NAME"; printf '\n'; printf 'xui='; systemctl list-unit-files 2>/dev/null | grep -E '^(x-ui|3x-ui)\.service' | tr '\n' ','; printf '\nxray='; systemctl list-unit-files 2>/dev/null | grep '^xray\.service' | tr '\n' ','; printf '\nnginx='; systemctl list-unit-files 2>/dev/null | grep '^nginx\.service' | tr '\n' ','; printf '\ndocker='; command -v docker >/dev/null 2>&1 && printf 'installed' || printf 'absent'; printf '\nyadrenovpn='; pgrep -af 'YadrenoVPN|yadrenovpn' 2>/dev/null | head -3 | tr '\n' ';'; printf '\nopenclaw='; command -v openclaw >/dev/null 2>&1 && printf 'installed' || printf 'absent'; printf '\nopenclaw_gateway='; systemctl --user is-active openclaw-gateway 2>/dev/null || true; printf '\n'''
    try:
        rc, out = _run_ssh(row, probe)
        ok = rc == 0 and "__XFI__" in out
        with _db() as conn:
            conn.execute("UPDATE vps SET last_check=?,last_ok=?,last_error=? WHERE id=?", (time.time(), int(ok), "" if ok else out[-1000:], vps_id))
            conn.commit()
        _audit("detect", row[2], "ok" if ok else out[-1000:])
        return {"ok": ok, "raw": out}
    except Exception as exc:
        with _db() as conn:
            conn.execute("UPDATE vps SET last_check=?,last_ok=0,last_error=? WHERE id=?", (time.time(), str(exc)[:1000], vps_id))
            conn.commit()
        _audit("detect", row[2], str(exc))
        return {"ok": False, "error": str(exc)}


def safe_restart(vps_id: int, service: str):
    allowed = {"x-ui", "3x-ui", "xray", "nginx", "docker"}
    if service not in allowed:
        raise ValueError("Service is not allowed")
    with _db() as conn:
        row = conn.execute("SELECT id,name,host,port,username,auth_type,auth_value FROM vps WHERE id=?", (vps_id,)).fetchone()
    if not row:
        raise KeyError("VPS not found")
    remote = f"systemctl is-active --quiet {shlex.quote(service)} && systemctl restart {shlex.quote(service)} && systemctl is-active {shlex.quote(service)} || systemctl is-active {shlex.quote(service)}"
    rc, out = _run_ssh(row, remote)
    ok = rc == 0 and out.splitlines()[-1:] == ["active"]
    _audit("restart", f"{row[2]}:{service}", "ok" if ok else out[-1000:])
    return {"ok": ok, "service": service, "status": out}
