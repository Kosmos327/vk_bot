import logging
import os
import random
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError

from db import (
    add_user_if_not_exists,
    add_partner,
    approve_latest_request,
    count_requests,
    count_users,
    create_request,
    get_user_by_vk_id,
    list_active_partners,
    list_partners,
    init_db,
    list_active_users,
    list_expired_users,
    list_pending_requests,
    list_requests,
    mark_latest_request_receipt,
    get_user_details,
    set_partner_active,
    set_latest_request_status,
    touch_user_activity,
)
from keyboards import (
    BUTTON_ADMIN_ACTIVE,
    BUTTON_ADMIN_EXPIRED,
    BUTTON_ADMIN_PENDING,
    BUTTON_ADMIN_PARTNERS,
    BUTTON_ADMIN_REQUESTS,
    BUTTON_ADMIN_STATS,
    BUTTON_BENEFITS,
    BUTTON_PAID,
    BUTTON_PARTNERS,
    BUTTON_PAYMENT,
    BUTTON_QUESTION,
    get_admin_keyboard,
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
from scheduler import scheduler_loop


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("vk_bot")


PAID_CONFIRMATION_TEXT = "Отлично, отправь скрин оплаты. Администратор проверит и даст доступ."
RECEIPT_RECEIVED_TEXT = "Скрин оплаты получен ✅ Администратор проверит оплату и выдаст доступ."
NO_REQUEST_FOR_RECEIPT_TEXT = "Я получил файл, но сначала нажми «Как оплатить», чтобы создать заявку."


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
        return build_partners_response()
    if text == BUTTON_QUESTION.lower():
        return QUESTION_TEXT
    return UNKNOWN_TEXT


def send_message(vk_api, peer_id: int, text: str, keyboard: Optional[str] = None) -> None:
    vk_api.messages.send(
        peer_id=peer_id,
        message=text,
        random_id=random.randint(1, 2_147_483_647),
        keyboard=keyboard or get_main_keyboard(),
    )


def _safe_text(value: Optional[str]) -> str:
    return value if value else "—"


def build_partners_response() -> str:
    partners = list_active_partners()
    if not partners:
        return PARTNERS_TEXT

    lines = ["Партнёры АвтоКлуб НСК:\n"]
    for idx, (_, name, category, discount, address, phone, _) in enumerate(partners, start=1):
        lines.append(
            f"{idx}. {name}\n"
            f"Категория: {_safe_text(category)}\n"
            f"Скидка: {_safe_text(discount)}\n"
            f"Адрес: {_safe_text(address)}\n"
            f"Телефон: {_safe_text(phone)}"
        )
    return "\n\n".join(lines)


def send_admin_notification(vk_api, admin_id: int, vk_id: int, status: str) -> None:
    user = get_user_by_vk_id(vk_id)
    first_name = user[1] if user else ""
    last_name = user[2] if user else ""
    admin_text = (
        "Новая заявка\n"
        f"ID пользователя: {vk_id}\n"
        f"Имя: {first_name} {last_name}".strip()
        + f"\nСтатус: {status}"
    )
    send_message(vk_api, peer_id=admin_id, text=admin_text)


def send_receipt_notification(vk_api, admin_id: int, vk_id: int) -> None:
    user = get_user_by_vk_id(vk_id)
    first_name = user[1] if user else ""
    last_name = user[2] if user else ""
    admin_text = (
        "Поступил скрин оплаты\n"
        f"ID пользователя: {vk_id}\n"
        f"Имя: {first_name} {last_name}\n"
        "Статус: paid"
    )
    send_message(vk_api, peer_id=admin_id, text=admin_text)


def save_user(vk_api, from_id: int) -> None:
    user_info = vk_api.users.get(user_ids=from_id)
    if not user_info:
        return
    profile = user_info[0]
    add_user_if_not_exists(
        vk_id=from_id,
        first_name=profile.get("first_name", ""),
        last_name=profile.get("last_name", ""),
    )


def has_receipt_attachment(message: dict) -> bool:
    attachments = message.get("attachments", [])
    for attachment in attachments:
        attachment_type = attachment.get("type")
        if attachment_type in {"photo", "doc"}:
            return True
    return False


def build_approved_text(club_invite_link: str, access_until: str) -> str:
    return (
        "Оплата подтверждена ✅\n\n"
        "Добро пожаловать в АвтоКлуб НСК!\n\n"
        "Ссылка для входа в закрытый клуб:\n"
        f"{club_invite_link}\n\n"
        f"Доступ действует до: {access_until}"
    )


def handle_admin_command(
    vk_api,
    text: str,
    admin_id: int,
    club_invite_link: str,
    raw_text: str,
) -> bool:
    if text == "/admin":
        send_message(
            vk_api,
            peer_id=admin_id,
            text="Админ-панель АвтоКлуб НСК",
            keyboard=get_admin_keyboard(),
        )
        return True

    if text == normalize_text(BUTTON_ADMIN_STATS):
        text = "/stats"
    elif text == normalize_text(BUTTON_ADMIN_PENDING):
        text = "/pending"
    elif text == normalize_text(BUTTON_ADMIN_ACTIVE):
        text = "/active"
    elif text == normalize_text(BUTTON_ADMIN_EXPIRED):
        text = "/expired"
    elif text == normalize_text(BUTTON_ADMIN_REQUESTS):
        text = "/requests"
    elif text == normalize_text(BUTTON_ADMIN_PARTNERS):
        text = "/partners"

    if text == "/users":
        send_message(vk_api, peer_id=admin_id, text=f"Пользователей: {count_users()}")
        return True

    if text == "/requests":
        requests = list_requests()
        if not requests:
            send_message(vk_api, peer_id=admin_id, text="Заявок пока нет")
            return True

        lines = [
            f"{vk_id} | {status} | {receipt_received} | {created_at} | {approved_at or '-'} | {access_until or '-'}"
            for vk_id, status, receipt_received, created_at, approved_at, access_until in requests
        ]
        send_message(vk_api, peer_id=admin_id, text="\n".join(lines))
        return True

    if text == "/pending":
        requests = list_pending_requests()
        if not requests:
            send_message(vk_api, peer_id=admin_id, text="Нет заявок в статусе paid")
            return True

        lines = [
            f"{vk_id} | {status} | {receipt_received} | {created_at}\nПодтвердить: /approve {vk_id}"
            for vk_id, status, receipt_received, created_at in requests
        ]
        send_message(vk_api, peer_id=admin_id, text="\n\n".join(lines))
        return True

    if text.startswith("/approve "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            return True

        vk_id = int(parts[1])
        approved_data = approve_latest_request(vk_id=vk_id)
        if not approved_data:
            send_message(vk_api, peer_id=admin_id, text="У пользователя нет заявок")
            return True

        if not club_invite_link:
            send_message(vk_api, peer_id=admin_id, text="Ошибка: CLUB_INVITE_LINK не заполнен в .env")
            return True

        access_until, is_renewal = approved_data
        send_message(vk_api, peer_id=vk_id, text=build_approved_text(club_invite_link, access_until))
        renewal_note = " (продление)" if is_renewal else ""
        send_message(
            vk_api,
            peer_id=admin_id,
            text=f"Пользователь {vk_id} подтверждён{renewal_note}, ссылка отправлена.",
        )
        return True

    if text == "/active":
        active_users = list_active_users()
        if not active_users:
            send_message(vk_api, peer_id=admin_id, text="Нет пользователей с активным доступом")
            return True

        lines = [f"{vk_id} | {access_until}" for vk_id, access_until in active_users]
        send_message(vk_api, peer_id=admin_id, text="\n".join(lines))
        return True

    if text == "/expired":
        expired_users = list_expired_users()
        if not expired_users:
            send_message(vk_api, peer_id=admin_id, text="Нет пользователей с истёкшим доступом")
            return True

        lines = [f"{vk_id} | {access_until}" for vk_id, access_until in expired_users]
        send_message(vk_api, peer_id=admin_id, text="\n".join(lines))
        return True

    if text.startswith("/user "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            return True

        vk_id = int(parts[1])
        user_details = get_user_details(vk_id)
        if not user_details:
            send_message(vk_api, peer_id=admin_id, text="Пользователь не найден")
            return True

        (
            user_vk_id,
            first_name,
            last_name,
            first_message_at,
            status,
            receipt_received,
            request_created_at,
            approved_at,
            access_until,
            is_renewal,
        ) = user_details

        details_text = (
            f"vk_id: {user_vk_id}\n"
            f"имя: {first_name} {last_name}\n"
            f"дата первого сообщения: {first_message_at}\n"
            f"последняя заявка: {request_created_at or '-'}\n"
            f"статус: {status or '-'}\n"
            f"receipt_received: {receipt_received if receipt_received is not None else '-'}\n"
            f"approved_at: {approved_at or '-'}\n"
            f"access_until: {access_until or '-'}\n"
            f"is_renewal: {is_renewal if is_renewal is not None else '-'}"
        )
        send_message(vk_api, peer_id=admin_id, text=details_text)
        return True

    if text == "/stats":
        stats_text = f"Пользователей: {count_users()}\nЗаявок: {count_requests()}"
        send_message(vk_api, peer_id=admin_id, text=stats_text)
        return True

    if text == "/partners":
        partners = list_partners()
        if not partners:
            send_message(vk_api, peer_id=admin_id, text="Партнёров пока нет")
            return True

        lines = [f"{partner_id} | {name} | {category or '-'} | {discount or '-'} | {is_active}" for partner_id, name, category, discount, is_active in partners]
        send_message(vk_api, peer_id=admin_id, text="\n".join(lines))
        return True

    if text.startswith("/partneroff "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_message(vk_api, peer_id=admin_id, text="Формат: /partneroff {id}")
            return True

        partner_id = int(parts[1])
        if not set_partner_active(partner_id=partner_id, is_active=0):
            send_message(vk_api, peer_id=admin_id, text="Партнёр с таким id не найден")
            return True
        send_message(vk_api, peer_id=admin_id, text=f"Партнёр {partner_id} деактивирован")
        return True

    if text.startswith("/partneron "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_message(vk_api, peer_id=admin_id, text="Формат: /partneron {id}")
            return True

        partner_id = int(parts[1])
        if not set_partner_active(partner_id=partner_id, is_active=1):
            send_message(vk_api, peer_id=admin_id, text="Партнёр с таким id не найден")
            return True
        send_message(vk_api, peer_id=admin_id, text=f"Партнёр {partner_id} активирован")
        return True

    if text.startswith("/addpartner"):
        parts = [part.strip() for part in raw_text.split("|")]
        if len(parts) != 7 or parts[0].strip().lower() != "/addpartner":
            send_message(
                vk_api,
                peer_id=admin_id,
                text=(
                    "Формат:\n"
                    "/addpartner | Название | Категория | Скидка | Адрес | Телефон | Описание"
                ),
            )
            return True

        _, name, category, discount, address, phone, description = parts
        if not name:
            send_message(vk_api, peer_id=admin_id, text="Название партнёра обязательно")
            return True

        partner_id = add_partner(
            name=name,
            category=category,
            discount=discount,
            address=address,
            phone=phone,
            description=description,
        )
        send_message(vk_api, peer_id=admin_id, text=f"Партнёр добавлен с id={partner_id}")
        return True

    return False


def handle_business_actions(vk_api, text: str, from_id: int, admin_id: int) -> Optional[str]:
    if text == BUTTON_PAYMENT.lower():
        create_request(vk_id=from_id, status="new")
        send_admin_notification(vk_api, admin_id=admin_id, vk_id=from_id, status="new")
        return PAYMENT_TEXT

    if text == BUTTON_PAID.lower():
        updated = set_latest_request_status(vk_id=from_id, status="paid")
        if updated:
            send_admin_notification(vk_api, admin_id=admin_id, vk_id=from_id, status="paid")
            return PAID_CONFIRMATION_TEXT
        return "У тебя пока нет заявки. Нажми «Как оплатить», чтобы создать заявку."

    return None


def handle_receipt(vk_api, from_id: int, peer_id: int, admin_id: int) -> bool:
    updated_status = mark_latest_request_receipt(vk_id=from_id)
    if updated_status is None:
        send_message(vk_api, peer_id=peer_id, text=NO_REQUEST_FOR_RECEIPT_TEXT)
        return True

    send_message(vk_api, peer_id=peer_id, text=RECEIPT_RECEIVED_TEXT)
    send_receipt_notification(vk_api, admin_id=admin_id, vk_id=from_id)
    return True


def main() -> None:
    load_dotenv()

    group_token = get_env("VK_GROUP_TOKEN")
    group_id = int(get_env("VK_GROUP_ID"))
    admin_id = int(get_env("ADMIN_ID"))
    club_invite_link = os.getenv("CLUB_INVITE_LINK", "").strip()

    init_db()

    vk_session = VkApi(token=group_token)
    longpoll = VkBotLongPoll(vk_session, group_id)
    vk_api = vk_session.get_api()

    scheduler_thread = threading.Thread(
        target=scheduler_loop,
        args=(vk_api,),
        daemon=True,
        name="reminder-scheduler",
    )
    scheduler_thread.start()

    logger.info("Бот запущен и слушает события Long Poll")

    while True:
        try:
            for event in longpoll.listen():
                if event.type != VkBotEventType.MESSAGE_NEW:
                    continue

                try:
                    message = event.object.message
                    raw_text = (message.get("text") or "").strip()
                    incoming_text = normalize_text(message.get("text"))
                    peer_id = message["peer_id"]
                    from_id = message.get("from_id")

                    if not from_id:
                        continue

                    save_user(vk_api, from_id)
                    touch_user_activity(from_id)

                    if from_id == admin_id and handle_admin_command(
                        vk_api, incoming_text, admin_id, club_invite_link, raw_text
                    ):
                        continue

                    if has_receipt_attachment(message):
                        if handle_receipt(vk_api, from_id=from_id, peer_id=peer_id, admin_id=admin_id):
                            continue

                    business_response = handle_business_actions(
                        vk_api, text=incoming_text, from_id=from_id, admin_id=admin_id
                    )
                    if business_response is not None:
                        send_message(vk_api, peer_id=peer_id, text=business_response)
                        continue

                    response = resolve_response(incoming_text)
                    send_message(vk_api, peer_id=peer_id, text=response)
                except ApiError:
                    logger.exception("Ошибка VK API при отправке сообщения")
                except Exception:
                    logger.exception("Ошибка при обработке входящего сообщения")
        except Exception:
            logger.exception("Критическая ошибка цикла Long Poll, перезапуск через 3 секунды")
            time.sleep(3)


if __name__ == "__main__":
    main()
