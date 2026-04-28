import logging
import os
import random
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.exceptions import ApiError

from db import (
    add_user_if_not_exists,
    add_partner,
    approve_latest_request,
    count_user_approved_referrals,
    count_requests,
    count_users,
    create_request,
    create_discount_code,
    confirm_discount_code_intent,
    count_user_discount_codes_today,
    get_vk_id_by_referral_code,
    get_active_discount_code_for_partner,
    get_active_partner_by_id,
    get_discount_code_details,
    get_pending_discount_code_intent,
    get_user_referral_details,
    get_user_by_vk_id,
    has_active_access,
    list_active_partners,
    list_partners,
    list_recent_discount_codes,
    list_referrers_by_approved_count,
    init_db,
    list_active_users,
    list_expired_users,
    list_pending_requests,
    list_requests,
    mark_latest_request_receipt,
    mark_referral_approved,
    get_user_details,
    set_user_referrer_if_empty,
    set_partner_active,
    set_latest_request_status,
    touch_user_activity,
    upsert_discount_code_intent,
    use_discount_code,
)
from keyboards import (
    BUTTON_ADMIN_ACTIVE,
    BUTTON_ADMIN_CODES,
    BUTTON_ADMIN_EXPIRED,
    BUTTON_ADMIN_PENDING,
    BUTTON_ADMIN_PARTNERS,
    BUTTON_ADMIN_REQUESTS,
    BUTTON_ADMIN_STATS,
    BUTTON_BENEFITS,
    BUTTON_PAID,
    BUTTON_PARTNERS,
    BUTTON_PAYMENT,
    BUTTON_MY_LINK,
    BUTTON_GET_DISCOUNT,
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


PAID_CONFIRMATION_TEXT = "Отлично, отправьте скрин оплаты. Администратор проверит и предоставит доступ."
RECEIPT_RECEIVED_TEXT = "Скрин оплаты получен ✅ Администратор проверит оплату и выдаст доступ."
NO_REQUEST_FOR_RECEIPT_TEXT = "Я получил файл, но сначала нажмите «Как оплатить», чтобы создать заявку."
REFERRAL_PATTERN = re.compile(r"^\s*(?:старт|start)\s+(AC\d+)\s*$", re.IGNORECASE)
DISCOUNT_PARTNER_PATTERN = re.compile(r"^\s*скидка\s+(\d+)\s*$", re.IGNORECASE)
DISCOUNT_CONFIRM_PATTERN = re.compile(r"^\s*да\s+(\d+)\s*$", re.IGNORECASE)


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


def send_admin_message(vk_api, admin_id: int, text: str) -> None:
    send_message(vk_api, peer_id=admin_id, text=text, keyboard=get_admin_keyboard())


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
    send_admin_message(vk_api, admin_id=admin_id, text=admin_text)


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
    send_admin_message(vk_api, admin_id=admin_id, text=admin_text)


def save_user(vk_api, from_id: int, referral_code: Optional[str] = None) -> None:
    user_info = vk_api.users.get(user_ids=from_id)
    if not user_info:
        return
    profile = user_info[0]
    add_user_if_not_exists(
        vk_id=from_id,
        first_name=profile.get("first_name", ""),
        last_name=profile.get("last_name", ""),
    )
    if referral_code:
        referrer_vk_id = get_vk_id_by_referral_code(referral_code.upper())
        if referrer_vk_id and referrer_vk_id != from_id:
            set_user_referrer_if_empty(vk_id=from_id, referrer_vk_id=referrer_vk_id)


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


def extract_referral_code(raw_text: str) -> Optional[str]:
    match = REFERRAL_PATTERN.match(raw_text or "")
    if not match:
        return None
    return match.group(1).upper()


def build_my_referral_text(group_id: int, vk_id: int) -> str:
    referral_code = f"AC{vk_id}"
    return (
        "Ваша реферальная ссылка:\n\n"
        f"https://vk.com/im?sel=-{group_id}&ref={referral_code}\n\n"
        "Приглашайте друзей в АвтоКлуб НСК.\n\n"
        f"Ваш код: {referral_code}\n"
        f"Друг может написать: СТАРТ {referral_code}"
    )


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_get_discount_response(vk_id: int) -> str:
    if not has_active_access(vk_id):
        return "Скидки доступны только участникам с активным доступом. Нажмите «Как оплатить», чтобы оформить доступ."

    partners = list_active_partners()
    if not partners:
        return "Сейчас нет активных партнёров со скидками."

    lines = ["Доступные партнёры:\n"]
    for partner_id, name, _, discount, _, _, _ in partners:
        lines.append(f"{partner_id}. {name} — {_safe_text(discount)}")
    lines.append(
        "\nВыберите партнёра только тогда, когда вы уже находитесь на месте и готовы воспользоваться скидкой.\n\n"
        "Код действует 15 минут.\n\n"
        "Чтобы выбрать партнёра, напишите:\n"
        "скидка {id}"
    )
    return "\n".join(lines)


def _handle_discount_partner_choice(text: str, from_id: int) -> Optional[str]:
    match = DISCOUNT_PARTNER_PATTERN.match(text)
    if not match:
        return None

    partner_id = int(match.group(1))
    if not has_active_access(from_id):
        return "Скидки доступны только участникам с активным доступом. Нажмите «Как оплатить», чтобы оформить доступ."

    partner = get_active_partner_by_id(partner_id)
    if not partner:
        return "Партнёр не найден или сейчас недоступен."

    _, partner_name, discount = partner
    intent_expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    upsert_discount_code_intent(vk_id=from_id, partner_id=partner_id, expires_at=intent_expires_at)

    return (
        "Вы выбрали партнёра:\n"
        f"{partner_name}\n\n"
        f"Скидка: {_safe_text(discount)}\n\n"
        "Код будет действовать 15 минут.\n"
        "Создавайте код только тогда, когда вы уже находитесь у партнёра.\n\n"
        "Создать код сейчас?\n\n"
        "Напишите:\n"
        f"ДА {partner_id}"
    )


def _handle_discount_confirmation(text: str, from_id: int) -> Optional[str]:
    match = DISCOUNT_CONFIRM_PATTERN.match(text)
    if not match:
        return None

    partner_id = int(match.group(1))
    if not has_active_access(from_id):
        return "Скидки доступны только участникам с активным доступом. Нажмите «Как оплатить», чтобы оформить доступ."

    partner = get_active_partner_by_id(partner_id)
    if not partner:
        return "Партнёр не найден или сейчас недоступен."

    intent = get_pending_discount_code_intent(vk_id=from_id, partner_id=partner_id)
    if not intent:
        return f"Подтверждение истекло. Напишите снова: скидка {partner_id}"

    intent_id, intent_expires_at = intent
    intent_expires_at_dt = _parse_iso(intent_expires_at)
    if not intent_expires_at_dt or intent_expires_at_dt <= datetime.utcnow():
        return f"Подтверждение истекло. Напишите снова: скидка {partner_id}"

    if count_user_discount_codes_today(from_id) >= 5:
        return "На сегодня достигнут лимит: не более 5 кодов в день."

    active_code = get_active_discount_code_for_partner(vk_id=from_id, partner_id=partner_id)
    if active_code:
        return "У вас уже есть активный код для этого партнёра. Используйте его или дождитесь окончания срока действия."

    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    code = ""
    for _ in range(10):
        candidate = f"AC-{random.randint(0, 999999):06d}"
        try:
            create_discount_code(code=candidate, vk_id=from_id, partner_id=partner_id, expires_at=expires_at)
            code = candidate
            break
        except sqlite3.IntegrityError:
            continue
    if not code:
        return f"Не удалось создать код. Пожалуйста, напишите ещё раз: ДА {partner_id}"
    confirm_discount_code_intent(intent_id=intent_id)

    _, partner_name, discount = partner
    return (
        "Ваш код скидки:\n\n"
        f"{code}\n\n"
        f"Партнёр: {partner_name}\n"
        f"Скидка: {_safe_text(discount)}\n"
        f"Действует до: {expires_at}\n\n"
        "Покажите этот код партнёру."
    )


def _check_or_use_code(code: str, mark_used: bool, admin_id: int) -> str:
    normalized_code = code.strip().upper()
    details = get_discount_code_details(normalized_code)
    if not details:
        return "Код не найден"

    (
        _id,
        _code,
        vk_id,
        partner_id,
        status,
        _created_at,
        expires_at,
        _used_at,
        _used_by_admin_id,
        first_name,
        last_name,
        discount,
    ) = details

    expires_at_dt = _parse_iso(expires_at)
    if status != "active":
        return "Код уже использован или недействителен"
    if not expires_at_dt or expires_at_dt < datetime.utcnow():
        return "Код истёк"

    partner = get_active_partner_by_id(partner_id)
    partner_name = partner[1] if partner else f"id={partner_id}"
    if mark_used:
        if use_discount_code(normalized_code, admin_id=admin_id):
            return "Код применён ✅"
        return "Код уже использован, истёк или недействителен"

    return (
        "Код действителен ✅\n"
        f"Участник: {first_name} {last_name}\n"
        f"VK ID: {vk_id}\n"
        f"Партнёр: {partner_name}\n"
        f"Скидка: {_safe_text(discount)}\n"
        f"Действует до: {expires_at}"
    )


def handle_admin_command(
    vk_api,
    text: str,
    admin_id: int,
    club_invite_link: str,
    raw_text: str,
) -> bool:
    if text == "/admin":
        send_admin_message(vk_api, admin_id=admin_id, text="Админ-панель АвтоКлуб НСК")
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
    elif text == normalize_text(BUTTON_ADMIN_CODES):
        text = "/codes"

    if text == "/users":
        send_admin_message(vk_api, admin_id=admin_id, text=f"Пользователей: {count_users()}")
        return True

    if text == "/checkcode":
        send_admin_message(vk_api, admin_id=admin_id, text="Формат: /checkcode {code}")
        return True

    if text.startswith("/checkcode "):
        parts = raw_text.split(maxsplit=1)
        if len(parts) != 2:
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /checkcode {code}")
            return True
        send_admin_message(
            vk_api,
            admin_id=admin_id,
            text=_check_or_use_code(parts[1], mark_used=False, admin_id=admin_id),
        )
        return True

    if text == "/usecode":
        send_admin_message(vk_api, admin_id=admin_id, text="Формат: /usecode {code}")
        return True

    if text.startswith("/usecode "):
        parts = raw_text.split(maxsplit=1)
        if len(parts) != 2:
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /usecode {code}")
            return True
        send_admin_message(
            vk_api,
            admin_id=admin_id,
            text=_check_or_use_code(parts[1], mark_used=True, admin_id=admin_id),
        )
        return True

    if text == "/codes":
        codes = list_recent_discount_codes(limit=20)
        if not codes:
            send_admin_message(vk_api, admin_id=admin_id, text="Кодов пока нет")
            return True
        lines = [
            f"{code} | {vk_id} | {partner_id} | {status} | {expires_at or '-'} | {used_at or '-'}"
            for code, vk_id, partner_id, status, expires_at, used_at in codes
        ]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text == "/requests":
        requests = list_requests()
        if not requests:
            send_admin_message(vk_api, admin_id=admin_id, text="Заявок пока нет")
            return True

        lines = [
            f"{vk_id} | {status} | {receipt_received} | {created_at} | {approved_at or '-'} | {access_until or '-'}"
            for vk_id, status, receipt_received, created_at, approved_at, access_until in requests
        ]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text == "/pending":
        requests = list_pending_requests()
        if not requests:
            send_admin_message(vk_api, admin_id=admin_id, text="Нет заявок в статусе paid")
            return True

        lines = [
            f"{vk_id} | {status} | {receipt_received} | {created_at}\nПодтвердить: /approve {vk_id}"
            for vk_id, status, receipt_received, created_at in requests
        ]
        send_admin_message(vk_api, admin_id=admin_id, text="\n\n".join(lines))
        return True

    if text == "/approve":
        send_admin_message(vk_api, admin_id=admin_id, text="Формат: /approve {vk_id}")
        return True

    if text.startswith("/approve "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /approve {vk_id}")
            return True

        if not club_invite_link:
            send_admin_message(
                vk_api,
                admin_id=admin_id,
                text="Ошибка: CLUB_INVITE_LINK не заполнен в .env. Заявка не подтверждена.",
            )
            return True

        vk_id = int(parts[1])
        approved_data = approve_latest_request(vk_id=vk_id)
        if not approved_data:
            send_admin_message(
                vk_api,
                admin_id=admin_id,
                text="Нет оплаченной заявки со скрином для подтверждения. Проверьте /pending.",
            )
            return True

        access_until, is_renewal = approved_data
        mark_referral_approved(vk_id)
        send_message(vk_api, peer_id=vk_id, text=build_approved_text(club_invite_link, access_until))
        renewal_note = " (продление)" if is_renewal else ""
        send_admin_message(
            vk_api,
            admin_id=admin_id,
            text=f"Пользователь {vk_id} подтверждён{renewal_note}, ссылка отправлена.",
        )
        return True

    if text == "/active":
        active_users = list_active_users()
        if not active_users:
            send_admin_message(vk_api, admin_id=admin_id, text="Нет пользователей с активным доступом")
            return True

        lines = [f"{vk_id} | {access_until}" for vk_id, access_until in active_users]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text == "/expired":
        expired_users = list_expired_users()
        if not expired_users:
            send_admin_message(vk_api, admin_id=admin_id, text="Нет пользователей с истёкшим доступом")
            return True

        lines = [f"{vk_id} | {access_until}" for vk_id, access_until in expired_users]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text == "/user":
        send_admin_message(vk_api, admin_id=admin_id, text="Формат: /user {vk_id}")
        return True

    if text.startswith("/user "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /user {vk_id}")
            return True

        vk_id = int(parts[1])
        user_details = get_user_details(vk_id)
        if not user_details:
            send_admin_message(vk_api, admin_id=admin_id, text="Пользователь не найден")
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
        send_admin_message(vk_api, admin_id=admin_id, text=details_text)
        return True

    if text == "/stats":
        stats_text = f"Пользователей: {count_users()}\nЗаявок: {count_requests()}"
        send_admin_message(vk_api, admin_id=admin_id, text=stats_text)
        return True

    if text == "/referrals":
        referrals = list_referrers_by_approved_count()
        if not referrals:
            send_admin_message(vk_api, admin_id=admin_id, text="Подтверждённых рефералов пока нет")
            return True
        lines = [f"{referrer_vk_id} | {approved_count}" for referrer_vk_id, approved_count in referrals]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text.startswith("/refuser "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /refuser {vk_id}")
            return True
        vk_id = int(parts[1])
        details = get_user_referral_details(vk_id)
        if not details:
            send_admin_message(vk_api, admin_id=admin_id, text="Пользователь не найден")
            return True
        user_vk_id, referral_code, referrer_vk_id = details
        approved_count = count_user_approved_referrals(user_vk_id)
        send_admin_message(
            vk_api,
            admin_id=admin_id,
            text=(
                f"vk_id: {user_vk_id}\n"
                f"referral_code: {referral_code or '-'}\n"
                f"referrer_vk_id: {referrer_vk_id if referrer_vk_id is not None else '-'}\n"
                f"approved_referrals: {approved_count}"
            ),
        )
        return True

    if text == "/partners":
        partners = list_partners()
        if not partners:
            send_admin_message(vk_api, admin_id=admin_id, text="Партнёров пока нет")
            return True

        lines = [f"{partner_id} | {name} | {category or '-'} | {discount or '-'} | {is_active}" for partner_id, name, category, discount, is_active in partners]
        send_admin_message(vk_api, admin_id=admin_id, text="\n".join(lines))
        return True

    if text.startswith("/partneroff "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /partneroff {id}")
            return True

        partner_id = int(parts[1])
        if not set_partner_active(partner_id=partner_id, is_active=0):
            send_admin_message(vk_api, admin_id=admin_id, text="Партнёр с таким id не найден")
            return True
        send_admin_message(vk_api, admin_id=admin_id, text=f"Партнёр {partner_id} деактивирован")
        return True

    if text.startswith("/partneron "):
        parts = text.split()
        if len(parts) != 2 or not parts[1].isdigit():
            send_admin_message(vk_api, admin_id=admin_id, text="Формат: /partneron {id}")
            return True

        partner_id = int(parts[1])
        if not set_partner_active(partner_id=partner_id, is_active=1):
            send_admin_message(vk_api, admin_id=admin_id, text="Партнёр с таким id не найден")
            return True
        send_admin_message(vk_api, admin_id=admin_id, text=f"Партнёр {partner_id} активирован")
        return True

    if text.startswith("/addpartner"):
        parts = [part.strip() for part in raw_text.split("|")]
        if len(parts) != 7 or parts[0].strip().lower() != "/addpartner":
            send_admin_message(
                vk_api,
                admin_id=admin_id,
                text=(
                    "Формат:\n"
                    "/addpartner | Название | Категория | Скидка | Адрес | Телефон | Описание"
                ),
            )
            return True

        _, name, category, discount, address, phone, description = parts
        if not name:
            send_admin_message(vk_api, admin_id=admin_id, text="Название партнёра обязательно")
            return True

        partner_id = add_partner(
            name=name,
            category=category,
            discount=discount,
            address=address,
            phone=phone,
            description=description,
        )
        send_admin_message(vk_api, admin_id=admin_id, text=f"Партнёр добавлен с id={partner_id}")
        return True

    return False


def handle_business_actions(vk_api, text: str, from_id: int, admin_id: int, group_id: int) -> Optional[str]:
    if text == BUTTON_PAYMENT.lower():
        create_request(vk_id=from_id, status="new")
        send_admin_notification(vk_api, admin_id=admin_id, vk_id=from_id, status="new")
        return PAYMENT_TEXT

    if text == BUTTON_PAID.lower():
        updated = set_latest_request_status(vk_id=from_id, status="paid")
        if updated:
            send_admin_notification(vk_api, admin_id=admin_id, vk_id=from_id, status="paid")
            return PAID_CONFIRMATION_TEXT
        return "У вас пока нет заявки. Нажмите «Как оплатить», чтобы создать заявку."

    if text == BUTTON_MY_LINK.lower():
        return build_my_referral_text(group_id=group_id, vk_id=from_id)

    if text == BUTTON_GET_DISCOUNT.lower():
        return _build_get_discount_response(from_id)

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

                    referral_code = extract_referral_code(raw_text)
                    if referral_code:
                        incoming_text = "start"
                    save_user(vk_api, from_id, referral_code=referral_code)
                    touch_user_activity(from_id)

                    if from_id == admin_id and handle_admin_command(
                        vk_api, incoming_text, admin_id, club_invite_link, raw_text
                    ):
                        continue

                    if has_receipt_attachment(message):
                        if handle_receipt(vk_api, from_id=from_id, peer_id=peer_id, admin_id=admin_id):
                            continue

                    business_response = handle_business_actions(
                        vk_api, text=incoming_text, from_id=from_id, admin_id=admin_id, group_id=group_id
                    )
                    if business_response is not None:
                        send_message(vk_api, peer_id=peer_id, text=business_response)
                        continue

                    discount_partner_response = _handle_discount_partner_choice(raw_text, from_id=from_id)
                    if discount_partner_response is not None:
                        send_message(vk_api, peer_id=peer_id, text=discount_partner_response)
                        continue

                    discount_confirm_response = _handle_discount_confirmation(raw_text, from_id=from_id)
                    if discount_confirm_response is not None:
                        send_message(vk_api, peer_id=peer_id, text=discount_confirm_response)
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
