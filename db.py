import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

DB_PATH = "database.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _migrate_requests_table(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "requests", "receipt_received"):
        conn.execute("ALTER TABLE requests ADD COLUMN receipt_received INTEGER DEFAULT 0")
    if not _column_exists(conn, "requests", "approved_at"):
        conn.execute("ALTER TABLE requests ADD COLUMN approved_at TEXT")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vk_id INTEGER UNIQUE,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vk_id INTEGER,
                status TEXT,
                created_at TEXT,
                receipt_received INTEGER DEFAULT 0,
                approved_at TEXT
            )
            """
        )
        _migrate_requests_table(conn)
        conn.commit()


def add_user_if_not_exists(vk_id: int, first_name: str, last_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users (vk_id, first_name, last_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (vk_id, first_name, last_name, _now()),
        )
        conn.commit()


def get_user_by_vk_id(vk_id: int) -> Optional[Tuple[int, str, str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT vk_id, first_name, last_name FROM users WHERE vk_id = ?",
            (vk_id,),
        ).fetchone()
        return row


def create_request(vk_id: int, status: str = "new") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO requests (vk_id, status, created_at) VALUES (?, ?, ?)",
            (vk_id, status, _now()),
        )
        conn.commit()


def get_latest_request(vk_id: int) -> Optional[Tuple[int, str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, status FROM requests WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
            (vk_id,),
        ).fetchone()
        return row


def mark_latest_request_receipt(vk_id: int) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, status FROM requests WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
            (vk_id,),
        ).fetchone()
        if not row:
            return None

        request_id, current_status = row
        new_status = current_status if current_status == "approved" else "paid"
        conn.execute(
            "UPDATE requests SET receipt_received = 1, status = ? WHERE id = ?",
            (new_status, request_id),
        )
        conn.commit()
        return new_status


def set_latest_request_status(vk_id: int, status: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM requests WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
            (vk_id,),
        ).fetchone()
        if not row:
            return False

        conn.execute("UPDATE requests SET status = ? WHERE id = ?", (status, row[0]))
        conn.commit()
        return True


def approve_latest_request(vk_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM requests WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
            (vk_id,),
        ).fetchone()
        if not row:
            return False

        conn.execute(
            "UPDATE requests SET status = ?, approved_at = ? WHERE id = ?",
            ("approved", _now(), row[0]),
        )
        conn.commit()
        return True


def list_requests() -> List[Tuple[int, str, int, str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT vk_id, status, receipt_received, created_at FROM requests ORDER BY id DESC"
        ).fetchall()
        return rows


def list_pending_requests() -> List[Tuple[int, str, int, str]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT vk_id, status, receipt_received, created_at
            FROM requests
            WHERE status = 'paid' AND (approved_at IS NULL OR approved_at = '')
            ORDER BY id DESC
            """
        ).fetchall()
        return rows


def count_users() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0


def count_requests() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM requests").fetchone()
        return row[0] if row else 0
