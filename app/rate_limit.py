import sqlite3
import time
from pathlib import Path


def consume_request(
    db_path: Path,
    key_id: int,
    rpm_limit: int,
    daily_limit: int,
) -> bool:
    """Atomically enforce a daily quota and a one-minute request window."""
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    rpm_limit = max(1, int(rpm_limit))
    daily_limit = max(1, int(daily_limit))

    with sqlite3.connect(db_path, timeout=10, isolation_level="IMMEDIATE") as conn:
        row = conn.execute(
            "SELECT requests_today, day, window_start, window_count "
            "FROM api_keys WHERE id=?",
            (key_id,),
        ).fetchone()
        if row is None:
            return False

        requests_today, stored_day, window_start, window_count = row
        if stored_day != day:
            requests_today = 0
        if window_start is None or now - float(window_start) >= 60:
            window_start = now
            window_count = 0

        if requests_today >= daily_limit or window_count >= rpm_limit:
            return False

        conn.execute(
            "UPDATE api_keys SET requests_today=?, day=?, window_start=?, "
            "window_count=?, last_used=? WHERE id=?",
            (
                requests_today + 1,
                day,
                window_start,
                window_count + 1,
                now,
                key_id,
            ),
        )
        return True
