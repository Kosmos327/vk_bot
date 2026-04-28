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


def _migrate_users_table(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "users", "last_activity_at"):
        conn.execute("ALTER TABLE users ADD COLUMN last_activity_at TEXT")
    if not _column_exists(conn, "users", "last_message_sent_at"):
        conn.execute("ALTER TABLE users ADD COLUMN last_message_sent_at TEXT")
    if not _column_exists(conn, "users", "referrer_vk_id"):
        conn.execute("ALTER TABLE users ADD COLUMN referrer_vk_id INTEGER")
    if not _column_exists(conn, "users", "referral_code"):
        conn.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
    conn.execute(
        """
        UPDATE users
        SET referral_code = 'AC' || vk_id
        WHERE referral_code IS NULL OR referral_code = ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code
        ON users(referral_code)
        """
    )


def _migrate_referrals_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_vk_id INTEGER,
            referred_vk_id INTEGER UNIQUE,
            created_at TEXT,
            approved_at TEXT
        )
        """
    )


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vk_id INTEGER UNIQUE,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT,
                last_activity_at TEXT,
                last_message_sent_at TEXT,
                referrer_vk_id INTEGER,
                referral_code TEXT UNIQUE
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                discount TEXT,
                address TEXT,
                phone TEXT,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                vk_id INTEGER NOT NULL,
                partner_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                expires_at TEXT,
                used_at TEXT,
                used_by_admin_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discount_code_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vk_id INTEGER NOT NULL,
                partner_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                expires_at TEXT
            )
            """
        )
        _migrate_users_table(conn)
        _migrate_requests_table(conn)
        _migrate_referrals_table(conn)
        conn.commit()


def add_partner(
    name: str,
    category: str,
    discount: str,
    address: str,
    phone: str,
    description: str,
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO partners (
                name,
                category,
                discount,
                address,
                phone,
                description,
                is_active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (name, category, discount, address, phone, description, _now()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_active_partners() -> List[Tuple[int, str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, discount, address, phone, description
            FROM partners
            WHERE is_active = 1
            ORDER BY id ASC
            """
        ).fetchall()
        return rows


def list_partners() -> List[Tuple[int, str, Optional[str], Optional[str], int]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, name, category, discount, is_active
            FROM partners
            ORDER BY id DESC
            """
        ).fetchall()
        return rows


def set_partner_active(partner_id: int, is_active: int) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT id FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE partners SET is_active = ? WHERE id = ?", (is_active, partner_id))
        conn.commit()
        return True


def add_user_if_not_exists(vk_id: int, first_name: str, last_name: str, referrer_vk_id: Optional[int] = None) -> None:
    referral_code = f"AC{vk_id}"
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users (
                vk_id,
                first_name,
                last_name,
                created_at,
                last_activity_at,
                referrer_vk_id,
                referral_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (vk_id, first_name, last_name, _now(), _now(), referrer_vk_id, referral_code),
        )
        conn.execute(
            """
            UPDATE users
            SET referral_code = COALESCE(NULLIF(referral_code, ''), ?)
            WHERE vk_id = ?
            """,
            (referral_code, vk_id),
        )
        conn.commit()


def get_vk_id_by_referral_code(referral_code: str) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT vk_id FROM users WHERE referral_code = ?",
            (referral_code,),
        ).fetchone()
        if not row:
            return None
        return int(row[0])


def set_user_referrer_if_empty(vk_id: int, referrer_vk_id: int) -> bool:
    if vk_id == referrer_vk_id:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT referrer_vk_id FROM users WHERE vk_id = ?",
            (vk_id,),
        ).fetchone()
        if not row:
            return False
        if row[0] is not None:
            return False
        conn.execute(
            "UPDATE users SET referrer_vk_id = ? WHERE vk_id = ?",
            (referrer_vk_id, vk_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO referrals (referrer_vk_id, referred_vk_id, created_at)
            VALUES (?, ?, ?)
            """,
            (referrer_vk_id, vk_id, _now()),
        )
        conn.commit()
        return True


def touch_user_activity(vk_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_activity_at = ? WHERE vk_id = ?",
            (_now(), vk_id),
        )
        conn.commit()


def get_last_message_sent_at(vk_id: int) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_message_sent_at FROM users WHERE vk_id = ?",
            (vk_id,),
        ).fetchone()
        if not row:
            return None
        return row[0]


def set_last_message_sent_at(vk_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_message_sent_at = ? WHERE vk_id = ?",
            (_now(), vk_id),
        )
        conn.commit()


def list_users_for_incomplete_payment_followup() -> List[Tuple[int, str, Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.vk_id, r.created_at, u.last_message_sent_at
            FROM requests r
            JOIN users u ON u.vk_id = r.vk_id
            WHERE r.id IN (
                SELECT MAX(id)
                FROM requests
                GROUP BY vk_id
            )
            AND r.status = 'new'
            """
        ).fetchall()
        return rows


def list_users_with_unapproved_receipt() -> List[Tuple[int, str, Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.vk_id, r.created_at, u.last_message_sent_at
            FROM requests r
            JOIN users u ON u.vk_id = r.vk_id
            WHERE r.id IN (
                SELECT MAX(id)
                FROM requests
                GROUP BY vk_id
            )
            AND r.status = 'paid'
            AND r.receipt_received = 1
            AND (r.approved_at IS NULL OR r.approved_at = '')
            """
        ).fetchall()
        return rows


def list_users_access_expiring_soon() -> List[Tuple[int, str, Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.vk_id, r.access_until, u.last_message_sent_at
            FROM requests r
            JOIN users u ON u.vk_id = r.vk_id
            WHERE r.id IN (
                SELECT MAX(id)
                FROM requests
                GROUP BY vk_id
            )
            AND r.status = 'approved'
            AND r.access_until IS NOT NULL
            """
        ).fetchall()
        return rows


def list_users_access_expired() -> List[Tuple[int, str, Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT r.vk_id, r.access_until, u.last_message_sent_at
            FROM requests r
            JOIN users u ON u.vk_id = r.vk_id
            WHERE r.id IN (
                SELECT MAX(id)
                FROM requests
                GROUP BY vk_id
            )
            AND r.status = 'approved'
            AND r.access_until IS NOT NULL
            """
        ).fetchall()
        return rows


def get_user_by_vk_id(vk_id: int) -> Optional[Tuple[int, str, str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT vk_id, first_name, last_name FROM users WHERE vk_id = ?",
            (vk_id,),
        ).fetchone()
        return row


def get_user_referral_details(vk_id: int) -> Optional[Tuple[int, Optional[str], Optional[int]]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT vk_id, referral_code, referrer_vk_id
            FROM users
            WHERE vk_id = ?
            """,
            (vk_id,),
        ).fetchone()
        return row


def mark_referral_approved(referred_vk_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            """
            UPDATE referrals
            SET approved_at = COALESCE(approved_at, ?)
            WHERE referred_vk_id = ?
            """,
            (_now(), referred_vk_id),
        )
        conn.commit()


def list_referrers_by_approved_count() -> List[Tuple[int, int]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT referrer_vk_id, COUNT(*) AS approved_count
            FROM referrals
            WHERE approved_at IS NOT NULL
            GROUP BY referrer_vk_id
            ORDER BY approved_count DESC, referrer_vk_id ASC
            """
        ).fetchall()
        return rows


def count_user_approved_referrals(referrer_vk_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM referrals
            WHERE referrer_vk_id = ? AND approved_at IS NOT NULL
            """,
            (referrer_vk_id,),
        ).fetchone()
        return row[0] if row else 0


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


def has_active_access(vk_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM requests
            WHERE vk_id = ? AND status = 'approved' AND access_until > ?
            ORDER BY access_until DESC
            LIMIT 1
            """,
            (vk_id, _now()),
        ).fetchone()
        return row is not None


def get_active_partner_by_id(partner_id: int) -> Optional[Tuple[int, str, Optional[str]]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, discount
            FROM partners
            WHERE id = ? AND is_active = 1
            """,
            (partner_id,),
        ).fetchone()
        return row


def upsert_discount_code_intent(vk_id: int, partner_id: int, expires_at: str) -> None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM discount_code_intents
            WHERE vk_id = ? AND partner_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (vk_id, partner_id),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE discount_code_intents
                SET created_at = ?, expires_at = ?, status = 'pending'
                WHERE id = ?
                """,
                (_now(), expires_at, row[0]),
            )
        else:
            conn.execute(
                """
                INSERT INTO discount_code_intents (vk_id, partner_id, status, created_at, expires_at)
                VALUES (?, ?, 'pending', ?, ?)
                """,
                (vk_id, partner_id, _now(), expires_at),
            )
        conn.commit()


def get_pending_discount_code_intent(vk_id: int, partner_id: int) -> Optional[Tuple[int, str]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, expires_at
            FROM discount_code_intents
            WHERE vk_id = ? AND partner_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (vk_id, partner_id),
        ).fetchone()
        return row


def confirm_discount_code_intent(intent_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE discount_code_intents SET status = 'confirmed' WHERE id = ?",
            (intent_id,),
        )
        conn.commit()


def count_user_discount_codes_today(vk_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM discount_codes
            WHERE vk_id = ? AND DATE(created_at) = DATE(?)
            """,
            (vk_id, _now()),
        ).fetchone()
        return row[0] if row else 0


def get_active_discount_code_for_partner(
    vk_id: int, partner_id: int
) -> Optional[Tuple[str, str]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT code, expires_at
            FROM discount_codes
            WHERE vk_id = ? AND partner_id = ? AND status = 'active' AND expires_at > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (vk_id, partner_id, _now()),
        ).fetchone()
        return row


def create_discount_code(code: str, vk_id: int, partner_id: int, expires_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO discount_codes (code, vk_id, partner_id, status, created_at, expires_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (code, vk_id, partner_id, _now(), expires_at),
        )
        conn.commit()


def get_discount_code_details(
    code: str,
) -> Optional[Tuple[int, str, int, int, str, Optional[str], Optional[str], Optional[str], Optional[int], str, str, Optional[str]]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                dc.id,
                dc.code,
                dc.vk_id,
                dc.partner_id,
                dc.status,
                dc.created_at,
                dc.expires_at,
                dc.used_at,
                dc.used_by_admin_id,
                COALESCE(u.first_name, ''),
                COALESCE(u.last_name, ''),
                p.discount
            FROM discount_codes dc
            LEFT JOIN users u ON u.vk_id = dc.vk_id
            LEFT JOIN partners p ON p.id = dc.partner_id
            WHERE dc.code = ?
            """,
            (code,),
        ).fetchone()
        return row


def list_recent_discount_codes(limit: int = 20) -> List[Tuple[str, int, int, str, Optional[str], Optional[str]]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT code, vk_id, partner_id, status, expires_at, used_at
            FROM discount_codes
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows


def use_discount_code(code: str, admin_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM discount_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            """
            UPDATE discount_codes
            SET status = 'used', used_at = ?, used_by_admin_id = ?
            WHERE code = ?
            """,
            (_now(), admin_id, code),
        )
        conn.commit()
        return True
