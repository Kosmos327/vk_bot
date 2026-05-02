from typing import Any

USER_STATE: dict[int, dict[str, Any]] = {}


def get_user_state(user_id: int) -> dict[str, Any]:
    return USER_STATE.setdefault(user_id, {})


def reset_user_state(user_id: int) -> None:
    USER_STATE.pop(user_id, None)
