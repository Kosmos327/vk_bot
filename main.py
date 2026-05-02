import logging
import random
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from vk_api import VkApi
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll

from config import load_config
from diagnostics import format_debug_status, format_health_status
from db import init_db
from keyboards import BUTTON_HELP, BUTTON_MAIN_MENU, BUTTON_MY_CODES, BUTTON_PARTNERS, BUTTON_SUBSCRIPTION, get_admin_keyboard, get_main_keyboard
from routing import is_legacy_confirm_command, is_legacy_discount_command, parse_code_command, parse_partner_command, parse_service_command
from scheduler import scheduler_loop
from services.backend_gateway import BackendApiError, BackendGateway
from state import USER_STATE, get_user_state, reset_user_state
from texts import HELP_TEXT, START_TEXT
from vk_attachments import extract_attachment_url

logger = logging.getLogger("vk_bot")
logging.basicConfig(level=logging.INFO)


def normalize_text(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def send_message(vk_api, peer_id: int, text: str, keyboard: Optional[str] = None) -> None:
    vk_api.messages.send(peer_id=peer_id, message=text, random_id=random.randint(1, 2_147_483_647), keyboard=keyboard or get_main_keyboard())


def main() -> None:
    load_dotenv()
    config = load_config()
    init_db()  # legacy admin compatibility

    if config.vk_bot_use_backend:
        logger.info("Running in backend API mode")
    else:
        logger.warning("VK_BOT_USE_BACKEND=false: running legacy SQLite mode")

    gateway = BackendGateway(config.backend_base_url, config.bot_api_token) if config.vk_bot_use_backend else None
    vk_session = VkApi(token=config.vk_group_token)
    longpoll = VkBotLongPoll(vk_session, config.vk_group_id)
    vk_api = vk_session.get_api()

    if not config.vk_bot_use_backend:
        threading.Thread(target=scheduler_loop, args=(vk_api,), daemon=True).start()

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue
        message = event.object.message
        peer_id = message["peer_id"]
        from_id = message.get("from_id")
        raw_text = (message.get("text") or "").strip()
        text = normalize_text(raw_text)
        if not from_id:
            continue

        try:
            if from_id == config.admin_id and text == "/debug":
                send_message(vk_api, peer_id, format_debug_status(config, user_state_size=len(USER_STATE)))
                continue

            if from_id == config.admin_id and text == "/health":
                send_message(vk_api, peer_id, format_health_status(config, gateway))
                continue

            if text in {"/debug", "/health"}:
                send_message(vk_api, peer_id, "Команда недоступна")
                continue

            if not config.vk_bot_use_backend:
                if from_id == config.admin_id and text == "/admin":
                    send_message(vk_api, peer_id, "Legacy SQLite admin mode", get_admin_keyboard())
                else:
                    send_message(vk_api, peer_id, "Бот работает в legacy-режиме. Доступны только legacy admin-команды.")
                continue

            if text in {"/start", "start", "начать"}:
                profile = vk_api.users.get(user_ids=from_id)[0]
                gateway.auth_vk_user(from_id, profile.get("first_name"), profile.get("last_name"), profile.get("screen_name"))
                send_message(vk_api, peer_id, START_TEXT)
                continue

            if text in {"партнёры", "партнеры", "получить скидку"}:
                text = normalize_text(BUTTON_PARTNERS)
            if text == "как оплатить":
                text = normalize_text(BUTTON_SUBSCRIPTION)

            if is_legacy_discount_command(raw_text):
                send_message(vk_api, peer_id, "Теперь скидка выбирается через услугу. Откройте партнёра и выберите услугу.")
                continue

            if is_legacy_confirm_command(raw_text):
                send_message(vk_api, peer_id, "Теперь код создаётся через команду «Код {id}» после выбора услуги.")
                continue

            if text == normalize_text(BUTTON_PARTNERS):
                categories = gateway.get_categories()
                if not categories:
                    send_message(vk_api, peer_id, "Пока нет активных партнёров. Загляните позже.")
                    continue
                state = get_user_state(from_id)
                state.clear()
                names = [c.get("name", "") for c in categories]
                state["categories"] = names
                send_message(vk_api, peer_id, "Выберите категорию:\n" + "\n".join(names))
                continue

            state = get_user_state(from_id)
            if raw_text in state.get("categories", []):
                state["last_category"] = raw_text
                partners = gateway.get_partners(category=raw_text, limit=10, offset=0)
                lines = [f"{i+1}. {p.get('name')} — {p.get('discount_description') or p.get('description') or 'без описания'}" for i, p in enumerate(partners)]
                lines.append("Чтобы открыть партнёра, напишите: Партнёр {id}")
                send_message(vk_api, peer_id, "\n".join(lines))
                continue

            pid = parse_partner_command(raw_text)
            if pid:
                partner = gateway.get_partner(pid)
                services = gateway.get_partner_services(pid)
                state["last_partner_id"] = pid
                card = f"{partner.get('name')}\nКатегория: {partner.get('category')}\nОписание: {partner.get('description') or '—'}"
                svc = [f"{s.get('id')}. {s.get('name')} — {s.get('discount') or s.get('price') or '—'}" for s in services]
                send_message(vk_api, peer_id, card + "\n\nУслуги:\n" + "\n".join(svc) + "\n\nЧтобы выбрать услугу, напишите: Услуга {service_id}")
                continue

            sid = parse_service_command(raw_text)
            if sid:
                last_partner_id = state.get("last_partner_id")
                if not last_partner_id:
                    send_message(vk_api, peer_id, "Сначала откройте партнёра из каталога.")
                    continue
                services = gateway.get_partner_services(last_partner_id)
                service = next((s for s in services if int(s.get("id", -1)) == sid), None)
                if not service:
                    send_message(vk_api, peer_id, "Услуга не найдена. Откройте карточку партнёра заново.")
                    continue
                send_message(vk_api, peer_id, f"{service.get('name')}\nОписание: {service.get('description') or '—'}\nСкидка: {service.get('discount') or '—'}\nЧтобы получить код, напишите: Код {sid}")
                continue

            cid = parse_code_command(raw_text)
            if cid:
                partner_id = state.get("last_partner_id")
                if not partner_id:
                    send_message(vk_api, peer_id, "Сначала откройте партнёра из каталога, затем выберите услугу и запросите код.")
                    continue
                code_data = gateway.request_discount_code(from_id, partner_id, cid)
                send_message(vk_api, peer_id, f"Ваш код: {code_data.get('code')}\nПартнёр: {code_data.get('partner_name')}\nУслуга: {code_data.get('service_name')}\nДействует до: {code_data.get('expires_at')}")
                continue

            if text == normalize_text(BUTTON_MY_CODES):
                codes = gateway.get_my_codes(from_id)
                send_message(vk_api, peer_id, "У вас пока нет кодов." if not codes else "\n".join([f"{c.get('code')} | {c.get('partner_name')} | {c.get('service_name')} | {c.get('status')} | до {c.get('expires_at') or '—'}" for c in codes]))
                continue

            if text == normalize_text(BUTTON_SUBSCRIPTION):
                sub = gateway.get_subscription(from_id)
                if sub.get("active"):
                    send_message(vk_api, peer_id, f"Подписка активна до: {sub.get('active_until')}")
                else:
                    latest = gateway.get_latest_payment_request(from_id)
                    send_message(vk_api, peer_id, f"Текущая заявка: {latest.get('status')}\nСумма: {latest.get('amount')}\n{latest.get('payment_instructions') or ''}\n\nЧтобы оформить подписку, напишите: Оплатить подписку" if latest else "Чтобы оформить подписку, напишите: Оплатить подписку")
                continue

            if text == "оплатить подписку":
                p = gateway.create_payment_request(from_id)
                get_user_state(from_id)["last_payment_request_id"] = p.get("id")
                send_message(vk_api, peer_id, f"Сумма: {p.get('amount')}\n{p.get('payment_instructions')}\nПосле оплаты нажмите «Я оплатил» и отправьте скрин оплаты.")
                continue

            if text == "я оплатил":
                gateway.mark_payment_paid(from_id)
                send_message(vk_api, peer_id, "Спасибо! Теперь отправьте скрин оплаты сюда в чат. Администратор проверит оплату.")
                continue

            file_url = extract_attachment_url(message)
            if file_url:
                gateway.attach_payment_receipt(from_id, file_url)
                send_message(vk_api, peer_id, "Скрин оплаты получен. Администратор проверит оплату и активирует подписку.")
                continue
            if message.get("attachments"):
                send_message(vk_api, peer_id, "Я получил файл, но не смог извлечь ссылку. Отправьте фото или документ с доступным URL.")
                continue

            if text in {normalize_text(BUTTON_HELP), "помощь"}:
                send_message(vk_api, peer_id, HELP_TEXT)
                continue
            if text in {normalize_text(BUTTON_MAIN_MENU), "меню"}:
                reset_user_state(from_id)
                send_message(vk_api, peer_id, "Главное меню", get_main_keyboard())
                continue

            if from_id == config.admin_id and text == "/admin":
                send_message(vk_api, peer_id, "Админ-панель (Legacy SQLite admin mode)", get_admin_keyboard())
                continue

            send_message(vk_api, peer_id, "Выберите действие в меню.")

        except BackendApiError as exc:
            if exc.code == "no_subscription":
                send_message(vk_api, peer_id, "Для получения кодов нужна активная подписка. Откройте раздел «💳 Подписка».")
            else:
                logger.warning("Backend API error code=%s status=%s", exc.code, exc.status_code)
                send_message(vk_api, peer_id, exc.message)
        except Exception:
            logger.exception("Ошибка обработки")
            send_message(vk_api, peer_id, "Произошла ошибка. Попробуйте позже.")
        time.sleep(0.01)


if __name__ == "__main__":
    main()
