import logging
import os
import random
from typing import Optional

from dotenv import load_dotenv
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError

from keyboards import (
    BUTTON_BENEFITS,
    BUTTON_PARTNERS,
    BUTTON_PAYMENT,
    BUTTON_QUESTION,
    get_main_keyboard,
)
from texts import (
    BENEFITS_TEXT,
    PARTNERS_TEXT,
    PAYMENT_TEXT,
    QUESTION_TEXT,
    TRIGGER_WORDS,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("vk_bot")


def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


def normalize_text(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def resolve_response(text: str) -> str:
    if text in TRIGGER_WORDS:
        return WELCOME_TEXT
    if text == BUTTON_BENEFITS.lower():
        return BENEFITS_TEXT
    if text == BUTTON_PAYMENT.lower():
        return PAYMENT_TEXT
    if text == BUTTON_PARTNERS.lower():
        return PARTNERS_TEXT
    if text == BUTTON_QUESTION.lower():
        return QUESTION_TEXT
    return UNKNOWN_TEXT


def send_message(vk_api, peer_id: int, text: str) -> None:
    vk_api.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=random.randint(1, 2_147_483_647),
        keyboard=get_main_keyboard(),
    )


def main() -> None:
    load_dotenv()

    group_token = get_env("VK_GROUP_TOKEN")
    group_id = int(get_env("VK_GROUP_ID"))

    vk_session = VkApi(token=group_token)
    longpoll = VkBotLongPoll(vk_session, group_id)
    vk_api = vk_session.get_api()

    logger.info("Бот запущен и слушает события Long Poll")

    while True:
        try:
            for event in longpoll.listen():
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue

                try:
                    incoming_text = normalize_text(event.object.message.get("text"))
                    peer_id = event.object.message["peer_id"]
                    response = resolve_response(incoming_text)
                    send_message(vk_api, peer_id=peer_id, text=response)
                except ApiError:
                    logger.exception("Ошибка VK API при отправке сообщения")
                except Exception:
                    logger.exception("Ошибка при обработке входящего сообщения")
        except Exception:
            logger.exception("Критическая ошибка цикла Long Poll, перезапуск через 3 секунды")
            import time

            time.sleep(3)


if __name__ == "__main__":
    main()
