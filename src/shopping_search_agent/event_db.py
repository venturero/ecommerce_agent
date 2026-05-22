from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL,
    url TEXT,
    domain TEXT,
    position INTEGER,
    message_text TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    session_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    click_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, domain)
);

CREATE TABLE IF NOT EXISTS query_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    query_text TEXT NOT NULL,
    route TEXT,
    path TEXT NOT NULL,
    outcome TEXT NOT NULL,
    ttfb_s REAL,
    total_s REAL NOT NULL,
    shortlist_count INTEGER,
    http_status INTEGER,
    error_detail TEXT,
    is_follow_up INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def get_db_path() -> Path:
    return Path(os.getenv("EVENT_DB_PATH", "data.db"))


def init_db(db_path: Path | None = None) -> Path:
    path = (db_path or get_db_path()).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
    return path


@contextmanager
def db_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = init_db(db_path)
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_event(
    *,
    event_type: str,
    session_id: str,
    url: str | None = None,
    domain: str | None = None,
    position: int | None = None,
    message_text: str | None = None,
    created_at: str | None = None,
) -> int:
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (
                event_type, session_id, url, domain, position, message_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_type, session_id, url, domain, position, message_text, timestamp),
        )
        return int(cursor.lastrowid)


def increment_preference(session_id: str, domain: str) -> None:
    if not domain:
        return
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO preferences (session_id, domain, click_count)
            VALUES (?, ?, 1)
            ON CONFLICT(session_id, domain)
            DO UPDATE SET click_count = click_count + 1
            """,
            (session_id, domain),
        )


def clear_session_preferences(session_id: str) -> None:
    with db_connection() as conn:
        conn.execute("DELETE FROM preferences WHERE session_id = ?", (session_id,))


def get_session_preferences(session_id: str) -> dict[str, int]:
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT domain, click_count FROM preferences WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    return {str(domain): int(click_count) for domain, click_count in rows}


def domain_click_count(session_id: str | None, domain: str) -> int:
    if not session_id:
        return 0
    normalized = normalize_domain(domain)
    if not normalized:
        return 0
    prefs = get_session_preferences(session_id)
    return prefs.get(normalized, 0)


def normalize_domain(domain: str) -> str:
    host = domain.lower().strip()
    if host.startswith("www."):
        return host[4:]
    return host


def insert_query_request(
    *,
    session_id: str,
    query_text: str,
    path: str,
    outcome: str,
    total_s: float,
    ttfb_s: float | None = None,
    route: str | None = None,
    shortlist_count: int | None = None,
    http_status: int | None = None,
    error_detail: str | None = None,
    is_follow_up: bool = False,
    created_at: str | None = None,
) -> int:
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    with db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO query_requests (
                session_id, query_text, route, path, outcome,
                ttfb_s, total_s, shortlist_count, http_status,
                error_detail, is_follow_up, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                query_text,
                route,
                path,
                outcome,
                ttfb_s,
                total_s,
                shortlist_count,
                http_status,
                error_detail,
                1 if is_follow_up else 0,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def backup_db(dest: Path | None = None) -> Path:
    """Copy the event database to a timestamped file (safe, non-destructive)."""
    source = init_db()
    if dest is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = source.parent / f"{source.stem}-backup-{stamp}{source.suffix}"
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def export_db_json(dest: Path) -> Path:
    """Export events, preferences, and query_requests to a JSON file."""
    import json

    path = init_db()
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        payload: dict[str, Any] = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "db_path": str(path),
            "events": [
                dict(row) for row in conn.execute("SELECT * FROM events ORDER BY id")
            ],
            "preferences": [
                dict(row) for row in conn.execute("SELECT * FROM preferences ORDER BY session_id, domain")
            ],
            "query_requests": [
                dict(row) for row in conn.execute("SELECT * FROM query_requests ORDER BY id")
            ],
        }
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest
