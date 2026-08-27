import sqlite3
import time
from pathlib import Path
import os

DB = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))

def init_metrics():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.execute("CREATE TABLE IF NOT EXISTS provider_metrics (provider TEXT PRIMARY KEY, requests INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, latency_ms REAL DEFAULT 0, disabled_until REAL DEFAULT 0, last_status INTEGER, updated_at REAL)")
        c.commit()

def record(provider: str, ok: bool, latency_ms: float, status: int):
    init_metrics()
    with sqlite3.connect(DB) as c:
        c.execute("INSERT INTO provider_metrics(provider,requests,failures,latency_ms,last_status,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET requests=requests+1, failures=failures+excluded.failures, latency_ms=excluded.latency_ms, last_status=excluded.last_status, updated_at=excluded.updated_at", (provider, 1, 0 if ok else 1, latency_ms, status, time.time()))
        c.commit()

def snapshot():
    init_metrics()
    with sqlite3.connect(DB) as c:
        return [dict(zip(("provider","requests","failures","latency_ms","disabled_until","last_status","updated_at"), row)) for row in c.execute("SELECT provider,requests,failures,latency_ms,disabled_until,last_status,updated_at FROM provider_metrics ORDER BY provider")]
