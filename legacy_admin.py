from __future__ import annotations

from typing import Optional

LEGACY_ADMIN_COMMANDS = {
    "/admin",
    "/addpartner",
    "/partners",
    "/partneroff",
    "/partneron",
    "/approve",
    "/requests",
    "/pending",
    "/active",
    "/expired",
    "/user",
    "/codes",
    "/checkcode",
    "/usecode",
    "/referrals",
    "/refuser",
}

LEGACY_WARNING_PREFIX = "Legacy SQLite admin command. Основной источник данных сейчас backend CRM."


def is_legacy_admin_command(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return False
    cmd = raw.split()[0].lower()
    return cmd in LEGACY_ADMIN_COMMANDS


def should_allow_legacy_admin_command(is_backend_mode: bool, from_id: int, admin_id: int) -> bool:
    if is_backend_mode:
        return from_id == admin_id
    return from_id == admin_id


def format_legacy_warning(message: str) -> str:
    return f"{LEGACY_WARNING_PREFIX}\n{message}"


def handle_legacy_admin_command(text: str) -> tuple[str, Optional[str]]:
    cmd = (text or "").strip().split()[0].lower() if text else ""
    if cmd == "/admin":
        return "Legacy SQLite admin mode", "admin"
    return "Команда обработана в legacy SQLite-контуре. Проверьте локальную database.db.", None
