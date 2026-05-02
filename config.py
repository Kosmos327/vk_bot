import os
from dataclasses import dataclass


@dataclass
class Config:
    vk_group_token: str
    vk_group_id: int
    admin_id: int
    club_invite_link: str
    backend_base_url: str
    bot_api_token: str
    vk_bot_use_backend: bool



def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


def _get_bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    return Config(
        vk_group_token=_get_required_env("VK_GROUP_TOKEN"),
        vk_group_id=int(_get_required_env("VK_GROUP_ID")),
        admin_id=int(_get_required_env("ADMIN_ID")),
        club_invite_link=os.getenv("CLUB_INVITE_LINK", "").strip(),
        backend_base_url=_get_required_env("BACKEND_BASE_URL"),
        bot_api_token=_get_required_env("BOT_API_TOKEN"),
        vk_bot_use_backend=_get_bool_env("VK_BOT_USE_BACKEND", default=True),
    )
