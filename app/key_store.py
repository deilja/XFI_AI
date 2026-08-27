import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))
KEY_PREFIX = "xfi_"


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY, name TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER DEFAULT 1)")
    conn.commit()
    return conn


def _hash(value: str) -> str:
    salt = os.getenv("XFI_AI_KEY_PEPPER", "").encode()
    return hashlib.sha256(salt + value.encode()).hexdigest()


def create_key(name: str) -> str:
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    with _db() as conn:
        conn.execute("INSERT INTO api_keys(name,key_hash) VALUES(?,?)", (name[:100], _hash(raw)))
    return raw


def valid_key(raw: str) -> bool:
    if not raw.startswith(KEY_PREFIX) or len(raw) < 20:
        return False
    with _db() as conn:
        row = conn.execute("SELECT key_hash,active FROM api_keys WHERE key_hash=?", (_hash(raw),)).fetchone()
    return bool(row and row[1] and hmac.compare_digest(row[0], _hash(raw)))
