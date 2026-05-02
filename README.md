# VK Bot — АвтоКлуб НСК

Бот работает как отдельный Long Poll процесс, а клиентская бизнес-логика вынесена в backend API (`autoclub_nsk_web`).

## Новая архитектура
- VK bot принимает сообщения через Long Poll.
- Для клиентских сценариев бот вызывает backend HTTP API.
- Единый source of truth: backend + PostgreSQL.
- SQLite (`db.py`) оставлен как legacy/fallback для старых админских частей.

## Переменные окружения
- `VK_GROUP_TOKEN`
- `VK_GROUP_ID`
- `ADMIN_ID`
- `BACKEND_BASE_URL`
- `BOT_API_TOKEN`
- `VK_BOT_USE_BACKEND=true|false` (по умолчанию true)
- `CLUB_INVITE_LINK` (legacy)

## Запуск
```bash
pip install -r requirements.txt
python main.py
```

Backend должен быть запущен и доступен по `BACKEND_BASE_URL`.

## Клиентские сценарии
- `/start` — авторизация пользователя в backend и показ главного меню.
- `🚗 Партнёры и скидки` — категории, партнёры, услуги и выдача кода через backend.
- `🎟 Мои коды` — список кодов из backend.
- `💳 Подписка` — статус подписки и создание заявки на оплату через backend.
- `Я оплатил` + вложение — отметка оплаты и отправка receipt URL в backend.
- `❓ Помощь` — инструкция для пользователя.

## Legacy
- `db.py` и SQLite не удалены, чтобы не ломать старые админ-команды и старые фоновые куски.
- Новые клиентские сценарии не используют локальные `create_discount_code/create_request/...`.
