import sqlite3
from pathlib import Path

from app.rate_limit import consume_request


def _db(path: Path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE api_keys (id INTEGER PRIMARY KEY, requests_today INTEGER, "
            "day TEXT, window_start REAL, window_count INTEGER, last_used REAL, "
            "rpm_limit INTEGER, daily_limit INTEGER)"
        )
        conn.execute(
            "INSERT INTO api_keys VALUES (1, 0, date('now'), 0, 0, NULL, 2, 3)"
        )
        conn.commit()


def test_rate_limit_enforces_rpm_and_daily_quota(tmp_path, monkeypatch):
    db = tmp_path / "keys.db"
    _db(db)
    now = 1_800_000_000.0
    monkeypatch.setattr("app.rate_limit.time.time", lambda: now)
    monkeypatch.setattr("app.rate_limit.time.strftime", lambda fmt, value: "2026-09-04")

    assert consume_request(db, 1, 2, 3) is True
    assert consume_request(db, 1, 2, 3) is True
    assert consume_request(db, 1, 2, 3) is False

    monkeypatch.setattr("app.rate_limit.time.time", lambda: now + 61)
    assert consume_request(db, 1, 2, 3) is True

    monkeypatch.setattr("app.rate_limit.time.time", lambda: now + 122)
    assert consume_request(db, 1, 2, 3) is False


def test_rate_limit_is_atomic_across_connections(tmp_path, monkeypatch):
    db = tmp_path / "keys.db"
    _db(db)
    monkeypatch.setattr("app.rate_limit.time.time", lambda: 1_800_000_000.0)
    monkeypatch.setattr("app.rate_limit.time.strftime", lambda fmt, value: "2026-09-04")

    assert consume_request(db, 1, 1, 100) is True
    assert consume_request(db, 1, 1, 100) is False
