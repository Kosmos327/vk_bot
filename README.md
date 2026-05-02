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

## Production smoke-check после деплоя

1. Проверить env:
   - `VK_GROUP_TOKEN`
   - `VK_GROUP_ID`
   - `ADMIN_ID`
   - `VK_BOT_USE_BACKEND=true`
   - `BACKEND_BASE_URL`
   - `BOT_API_TOKEN`
2. Запустить backend `autoclub_nsk_web`.
3. Запустить `vk_bot`.
4. В VK написать от админа:
   - `/debug`
   - `/health`
5. Клиентский путь:
   - `/start`
   - `🚗 Партнёры и скидки`
   - выбрать категорию
   - `Партнёр {id}`
   - `Услуга {id}`
   - `Код {id}`
6. Если нет подписки:
   - `💳 Подписка`
   - `Оплатить подписку`
   - `Я оплатил`
   - отправить скрин
   - проверить, что заявка появилась в web CRM.
7. В web CRM:
   - подтвердить оплату;
   - проверить, что подписка активировалась.
8. Вернуться в VK:
   - `💳 Подписка` показывает active;
   - `Код {id}` выдаётся при активной подписке.
9. Проверить `🎟 Мои коды`.
10. Проверить лимит:
   - повторный код у того же партнёра в этом месяце должен дать `monthly_limit`.

### Troubleshooting

- `backend_unavailable` — backend недоступен или таймаут; проверить доступность `BACKEND_BASE_URL` и сеть.
- `BOT_API_TOKEN missing` — не задан `BOT_API_TOKEN` при `VK_BOT_USE_BACKEND=true`.
- `401 from backend` — неверный `BOT_API_TOKEN` или backend отклоняет бот-токен.
- `no_subscription` — у пользователя неактивна подписка.
- `monthly_limit` — превышен месячный лимит выдачи кода у партнёра.
- `receipt URL not extracted` — VK вложение без извлекаемого URL; отправить фото/документ с доступной ссылкой.

## Legacy SQLite admin commands

Эти команды считаются legacy и работают только с локальной `database.db` через `db.py`:
- `/admin`
- `/addpartner`
- `/partners`
- `/partneroff`
- `/partneron`
- `/approve`
- `/requests`
- `/pending`
- `/active`
- `/expired`
- `/user`
- `/codes`
- `/checkcode`
- `/usecode`
- `/referrals`
- `/refuser`

Важно:
- Эти команды **НЕ управляют backend CRM**.
- Актуальные партнёры/услуги/коды/оплаты находятся в backend CRM.
- В `VK_BOT_USE_BACKEND=true` использование legacy-команд в production не рекомендуется.
- При вызове legacy-команд админ видит предупреждение: `Legacy SQLite admin command. Основной источник данных сейчас backend CRM.`

### Legacy scheduler
- Legacy SQLite scheduler автонапоминаний запускается только в `VK_BOT_USE_BACKEND=false`.
- В backend mode запуск отключён и логируется: `Legacy SQLite scheduler disabled in backend mode.`

### План будущей чистки
- После ручного smoke-check можно удалить legacy SQLite-контур или вынести его в отдельную ветку.
