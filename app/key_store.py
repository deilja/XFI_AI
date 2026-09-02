import hashlib
import os
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))
KEY_PREFIX = "xfi_"


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY, name TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1, rpm_limit INTEGER DEFAULT 60, daily_limit INTEGER DEFAULT 5000, requests_today INTEGER DEFAULT 0, day TEXT, last_used REAL)")
    conn.commit()
    return conn


def _hash(value: str) -> str:
    salt = os.getenv("XFI_AI_KEY_PEPPER", "").encode()
    return hashlib.sha256(salt + value.encode()).hexdigest()


def create_key(name: str, rpm_limit: int = 60, daily_limit: int = 5000) -> str:
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute("INSERT INTO api_keys(name,key_hash,rpm_limit,daily_limit,day) VALUES(?,?,?,?,date('now'))", (name[:100], _hash(raw), max(1, min(rpm_limit, 10000)), max(1, min(daily_limit, 1000000))))
    return raw


def key_info(raw: str):
    if not raw.startswith(KEY_PREFIX):
        return None
    with _db() as conn:
        row = conn.execute("SELECT id,name,active,rpm_limit,daily_limit,requests_today,day,last_used FROM api_keys WHERE key_hash=?", (_hash(raw),)).fetchone()
    return row


def valid_key(raw: str) -> bool:
    row = key_info(raw)
    return bool(row and row[2])


def consume(raw: str) -> bool:
    row = key_info(raw)
    if not row or not row[2]:
        return False
    now = time.time()
    current_day = time.strftime("%Y-%m-%d", time.gmtime(now))
    with _db() as conn:
        dbrow = conn.execute("SELECT requests_today,day,last_used,rpm_limit,daily_limit FROM api_keys WHERE id=?", (row[0],)).fetchone()
        count, day, last_used, rpm, daily = dbrow
        if day != current_day:
            count = 0
            day = current_day
        if count >= daily:
            return False
        if last_used and now - last_used < 60 / max(rpm, 1):
            return False
        conn.execute("UPDATE api_keys SET requests_today=?,day=?,last_used=? WHERE id=?", (count + 1, day, now, row[0]))
        conn.commit()
    return True


def list_keys():
    with _db() as conn:
        return [dict(zip(("id","name","created_at","active","rpm_limit","daily_limit","requests_today","last_used"), r)) for r in conn.execute("SELECT id,name,created_at,active,rpm_limit,daily_limit,requests_today,last_used FROM api_keys ORDER BY id DESC")]


def set_active(key_id: int, active: bool):
    with _db() as conn:
        conn.execute("UPDATE api_keys SET active=? WHERE id=?", (1 if active else 0, key_id))
        conn.commit()


def delete_key(key_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
        conn.commit()


def update_limits(key_id: int, rpm_limit: int, daily_limit: int):
    with _db() as conn:
        conn.execute("UPDATE api_keys SET rpm_limit=?,daily_limit=? WHERE id=?", (max(1, min(rpm_limit, 10000)), max(1, min(daily_limit, 1000000)), key_id))
        conn.commit()
