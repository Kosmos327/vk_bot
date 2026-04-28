import logging
import random
import time
from datetime import datetime, timedelta

from db import (
    get_last_message_sent_at,
    list_users_access_expired,
    list_users_access_expiring_soon,
    list_users_for_incomplete_payment_followup,
    list_users_with_unapproved_receipt,
    set_last_message_sent_at,
)
from keyboards import get_main_keyboard

logger = logging.getLogger("vk_bot.scheduler")

CHECK_INTERVAL_SECONDS = 600
SAME_MESSAGE_INTERVAL = timedelta(hours=24)
INCOMPLETE_PAYMENT_INTERVAL = timedelta(hours=2)
RECEIPT_WAIT_INTERVAL = timedelta(hours=1)
EXPIRE_SOON_INTERVAL = timedelta(days=2)
EXPIRED_INTERVAL = timedelta(days=1)

INCOMPLETE_PAYMENT_TEXT = (
    "Ты не завершил оформление доступа в АвтоКлуб НСК 🚗\n\n"
    "Напоминаю:\n"
    "— скидки на автоуслуги\n"
    "— участие в розыгрышах\n"
    "— закрытый клуб\n\n"
    "Стоимость: 349 ₽ / месяц\n\n"
    "Нажми «Как оплатить» и заверши доступ"
)

PAYMENT_RECEIVED_WAITING_TEXT = (
    "Мы получили твой платёж ✅\n\n"
    "Администратор скоро проверит оплату и выдаст доступ.\n"
    "Если долго нет ответа — напиши «оператор»"
)

ACCESS_EXPIRES_SOON_TEXT = (
    "Твой доступ в АвтоКлуб НСК скоро закончится ⚠️\n\n"
    "Продли доступ, чтобы не потерять:\n"
    "— скидки\n"
    "— участие в розыгрыше\n\n"
    "Стоимость продления: 349 ₽"
)

ACCESS_EXPIRED_TEXT = (
    "Твой доступ в АвтоКлуб НСК закончился ❌\n\n"
    "Ты больше не получаешь:\n"
    "— скидки\n"
    "— участие в розыгрышах\n\n"
    "Верни доступ за 349 ₽"
)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _can_send_message(vk_id: int, now: datetime) -> bool:
    last_sent_at = _parse_iso(get_last_message_sent_at(vk_id))
    if not last_sent_at:
        return True
    return (now - last_sent_at) >= SAME_MESSAGE_INTERVAL


def _send_message(vk_api, vk_id: int, text: str) -> None:
    vk_api.messages.send(
        peer_id=vk_id,
        message=text,
        random_id=random.randint(1, 2_147_483_647),
        keyboard=get_main_keyboard(),
    )


def _try_send_reminder(vk_api, vk_id: int, text: str, now: datetime) -> bool:
    if not _can_send_message(vk_id, now):
        return False

    _send_message(vk_api, vk_id, text)
    set_last_message_sent_at(vk_id)
    logger.info("Отправлено автонапоминание пользователю %s", vk_id)
    return True


def _process_incomplete_payment(vk_api, now: datetime) -> None:
    for vk_id, created_at_raw, _ in list_users_for_incomplete_payment_followup():
        created_at = _parse_iso(created_at_raw)
        if not created_at:
            continue

        if now - created_at < INCOMPLETE_PAYMENT_INTERVAL:
            continue

        _try_send_reminder(vk_api, vk_id=vk_id, text=INCOMPLETE_PAYMENT_TEXT, now=now)


def _process_unapproved_receipt(vk_api, now: datetime) -> None:
    for vk_id, created_at_raw, _ in list_users_with_unapproved_receipt():
        created_at = _parse_iso(created_at_raw)
        if not created_at:
            continue

        if now - created_at < RECEIPT_WAIT_INTERVAL:
            continue

        _try_send_reminder(vk_api, vk_id=vk_id, text=PAYMENT_RECEIVED_WAITING_TEXT, now=now)


def _process_expiring_access(vk_api, now: datetime) -> None:
    for vk_id, access_until_raw, _ in list_users_access_expiring_soon():
        access_until = _parse_iso(access_until_raw)
        if not access_until:
            continue

        delta = access_until - now
        if timedelta(days=1) < delta <= EXPIRE_SOON_INTERVAL:
            _try_send_reminder(vk_api, vk_id=vk_id, text=ACCESS_EXPIRES_SOON_TEXT, now=now)


def _process_expired_access(vk_api, now: datetime) -> None:
    for vk_id, access_until_raw, _ in list_users_access_expired():
        access_until = _parse_iso(access_until_raw)
        if not access_until:
            continue

        expired_for = now - access_until
        if expired_for >= EXPIRED_INTERVAL:
            _try_send_reminder(vk_api, vk_id=vk_id, text=ACCESS_EXPIRED_TEXT, now=now)


def scheduler_loop(vk_api) -> None:
    logger.info("Планировщик автонапоминаний запущен")

    while True:
        try:
            now = datetime.utcnow()
            _process_incomplete_payment(vk_api, now)
            _process_unapproved_receipt(vk_api, now)
            _process_expiring_access(vk_api, now)
            _process_expired_access(vk_api, now)
        except Exception:
            logger.exception("Ошибка в планировщике автонапоминаний")

        time.sleep(CHECK_INTERVAL_SECONDS)
