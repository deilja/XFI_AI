import os
import sqlite3
import time
from pathlib import Path

DB = Path(os.getenv("XFI_AI_DB", "/var/lib/xfi-ai/keys.db"))


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB, timeout=10)


def init_metrics():
    with _connect() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS provider_metrics ("
            "provider TEXT PRIMARY KEY, requests INTEGER DEFAULT 0, "
            "failures INTEGER DEFAULT 0, latency_ms REAL DEFAULT 0, "
            "disabled_until REAL DEFAULT 0, last_status INTEGER, updated_at REAL)"
        )
        c.commit()


def record(provider: str, ok: bool, latency_ms: float, status: int):
    init_metrics()
    now = time.time()
    with _connect() as c:
        row = c.execute(
            "SELECT failures FROM provider_metrics WHERE provider=?", (provider,)
        ).fetchone()
        failures = max(0, (row[0] if row else 0) - 1) if ok else (row[0] if row else 0) + 1
        if ok:
            disabled_until = 0.0
        elif status in (401, 403):
            disabled_until = now + 900
        elif status == 429:
            disabled_until = now + min(300, 15 * failures)
        elif status >= 500:
            disabled_until = now + min(60, 5 * failures)
        else:
            disabled_until = 0.0
        c.execute(
            "INSERT INTO provider_metrics(provider,requests,failures,latency_ms,disabled_until,last_status,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET "
            "requests=requests+1, failures=?, latency_ms=?, disabled_until=?, last_status=?, updated_at=?",
            (
                provider,
                1,
                failures,
                latency_ms,
                disabled_until,
                status,
                now,
                failures,
                latency_ms,
                disabled_until,
                status,
                now,
            ),
        )
        c.commit()


def provider_state(provider: str) -> dict[str, float]:
    init_metrics()
    with _connect() as c:
        row = c.execute(
            "SELECT failures, latency_ms, disabled_until FROM provider_metrics WHERE provider=?",
            (provider,),
        ).fetchone()
    if not row:
        return {}
    return {
        "failures": float(row[0] or 0),
        "latency": float(row[1] or 0) / 1000,
        "cooldown_until": float(row[2] or 0),
    }


def snapshot():
    init_metrics()
    with _connect() as c:
        return [
            dict(
                zip(
                    ("provider", "requests", "failures", "latency_ms", "disabled_until", "last_status", "updated_at"),
                    row,
                )
            )
            for row in c.execute(
                "SELECT provider,requests,failures,latency_ms,disabled_until,last_status,updated_at "
                "FROM provider_metrics ORDER BY provider"
            )
        ]
