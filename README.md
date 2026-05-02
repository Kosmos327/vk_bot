# VK Bot — АвтоКлуб НСК

Основной режим работы бота — **backend API mode** (`VK_BOT_USE_BACKEND=true`).

## Режимы

### 1) Backend mode (основной)
- Все клиентские сценарии идут через backend API.
- `db.py`/SQLite не используются для клиентского UX (каталог, коды, подписка, receipt).
- Требуемые env:
  - `VK_GROUP_TOKEN`
  - `VK_GROUP_ID`
  - `ADMIN_ID`
  - `BACKEND_BASE_URL`
  - `BOT_API_TOKEN`

### 2) Legacy mode (устаревший)
- Включается `VK_BOT_USE_BACKEND=false`.
- На старте логируется предупреждение: `VK_BOT_USE_BACKEND=false: running legacy SQLite mode`.
- SQLite (`database.db`, `db.py`) считается legacy и оставлен для старых admin-потоков.
- Клиентский новый UX в этом режиме не гарантируется.

## Команды и клиентский UX (backend mode)
- `/start`
- `🚗 Партнёры и скидки`
- `🎟 Мои коды`
- `💳 Подписка`
- `❓ Помощь`
- `Партнёр {id}`
- `Услуга {id}`
- `Код {id}`
- `Оплатить подписку`
- `Я оплатил`

## Устаревшие команды
- `скидка {id}` и `ДА {id}` — устарели, бот мягко направляет в новый flow.
- `Партнёры` и `Получить скидку` мапятся на `🚗 Партнёры и скидки`.
- `Как оплатить` мапится на `💳 Подписка`.

## Запуск
```bash
pip install -r requirements.txt
python main.py
```

Backend должен быть доступен по `BACKEND_BASE_URL` в backend mode.
