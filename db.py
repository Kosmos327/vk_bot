import sqlite3
from datetime import datetime, timedelta
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
    if not _column_exists(conn, "requests", "access_until"):
        conn.execute("ALTER TABLE requests ADD COLUMN access_until TEXT")
    if not _column_exists(conn, "requests", "is_renewal"):
        conn.execute("ALTER TABLE requests ADD COLUMN is_renewal INTEGER DEFAULT 0")


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
                approved_at TEXT,
                access_until TEXT,
                is_renewal INTEGER DEFAULT 0
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


def _calculate_access_period(conn: sqlite3.Connection, vk_id: int, now_iso: str) -> Tuple[str, int]:
    latest_active_row = conn.execute(
        """
        SELECT access_until
        FROM requests
        WHERE vk_id = ? AND status = 'approved' AND access_until IS NOT NULL AND access_until > ?
        ORDER BY access_until DESC
        LIMIT 1
        """,
        (vk_id, now_iso),
    ).fetchone()

    if latest_active_row and latest_active_row[0]:
        base_time = datetime.fromisoformat(latest_active_row[0])
        return (base_time + timedelta(days=30)).isoformat(), 1

    return (datetime.fromisoformat(now_iso) + timedelta(days=30)).isoformat(), 0


def approve_latest_request(vk_id: int) -> Optional[Tuple[str, int]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM requests WHERE vk_id = ? ORDER BY id DESC LIMIT 1",
            (vk_id,),
        ).fetchone()
        if not row:
            return None

        approved_at = _now()
        access_until, is_renewal = _calculate_access_period(conn, vk_id=vk_id, now_iso=approved_at)

        conn.execute(
            """
            UPDATE requests
            SET status = ?, approved_at = ?, access_until = ?, is_renewal = ?
            WHERE id = ?
            """,
            ("approved", approved_at, access_until, is_renewal, row[0]),
        )
        conn.commit()
        return access_until, is_renewal


def list_requests() -> List[Tuple[int, str, int, str, Optional[str], Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT vk_id, status, receipt_received, created_at, approved_at, access_until
            FROM requests
            ORDER BY id DESC
            """
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


def list_active_users() -> List[Tuple[int, str]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT vk_id, MAX(access_until) AS max_access_until
            FROM requests
            WHERE access_until IS NOT NULL
            GROUP BY vk_id
            HAVING max_access_until >= ?
            ORDER BY max_access_until ASC
            """,
            (_now(),),
        ).fetchall()
        return rows


def list_expired_users() -> List[Tuple[int, str]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT vk_id, MAX(access_until) AS max_access_until
            FROM requests
            WHERE access_until IS NOT NULL
            GROUP BY vk_id
            HAVING max_access_until < ?
            ORDER BY max_access_until DESC
            """,
            (_now(),),
        ).fetchall()
        return rows


def get_user_details(vk_id: int) -> Optional[Tuple]:
    with _connect() as conn:
        user_row = conn.execute(
            """
            SELECT vk_id, first_name, last_name, created_at
            FROM users
            WHERE vk_id = ?
            """,
            (vk_id,),
        ).fetchone()
        if not user_row:
            return None

        request_row = conn.execute(
            """
            SELECT status, receipt_received, created_at, approved_at, access_until, is_renewal
            FROM requests
            WHERE vk_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (vk_id,),
        ).fetchone()

        if not request_row:
            return (*user_row, None, None, None, None, None, None)

        return (*user_row, *request_row)
