from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from config import Config
from services.backend_gateway import BackendApiError, BackendGateway


def _sanitize_backend_url(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        return "missing"
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    return value


def mask_config_for_debug(config: Config) -> dict[str, str]:
    return {
        "VK_BOT_USE_BACKEND": "true" if config.vk_bot_use_backend else "false",
        "BACKEND_BASE_URL": _sanitize_backend_url(config.backend_base_url),
        "BOT_API_TOKEN": "configured" if config.bot_api_token else "missing",
        "VK_GROUP_ID": str(config.vk_group_id),
        "ADMIN_ID": str(config.admin_id),
    }


def format_debug_status(config: Config, user_state_size: int, legacy_admin_enabled: bool = True, legacy_scheduler_enabled: bool = False) -> str:
    data = mask_config_for_debug(config)
    lines = [
        "Debug status:",
        f"VK_BOT_USE_BACKEND: {data['VK_BOT_USE_BACKEND']}",
        f"BACKEND_BASE_URL: {data['BACKEND_BASE_URL']}",
        f"BOT_API_TOKEN: {data['BOT_API_TOKEN']}",
        f"VK_GROUP_ID: {data['VK_GROUP_ID']}",
        f"ADMIN_ID: {data['ADMIN_ID']}",
        f"USER_STATE size: {user_state_size}",
        f"legacy sqlite admin: {'enabled' if legacy_admin_enabled else 'disabled'}",
        f"legacy scheduler: {'enabled' if legacy_scheduler_enabled else 'disabled'}",
    ]
    if not config.vk_bot_use_backend:
        lines.append("Warning: legacy mode enabled (VK_BOT_USE_BACKEND=false).")
    return "\n".join(lines)


def format_health_status(config: Config, gateway: BackendGateway | None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    mode = "backend" if config.vk_bot_use_backend else "legacy"
    backend_url = _sanitize_backend_url(config.backend_base_url)

    lines = ["Health check:", f"Режим: {mode}", f"Backend: {backend_url}"]

    if not config.vk_bot_use_backend or gateway is None:
        lines.extend(["Связь с backend: N/A", "Проверка каталога: N/A", f"Время: {now}"])
        return "\n".join(lines)

    try:
        gateway.check_catalog_health()
        lines.extend(["Связь с backend: OK", "Проверка каталога: OK", f"Время: {now}"])
    except BackendApiError:
        lines.extend([
            "Связь с backend: FAIL",
            "Проверка каталога: FAIL",
            "Причина: Сервис временно недоступен. Попробуйте позже.",
            f"Время: {now}",
        ])
    return "\n".join(lines)
