# Telegram Calendar Bot Helper

MVP: приватный Telegram-бот для выбора слота, ручного согласования заявки и создания встречи в выделенном Google Calendar.

## Что уже есть в Этапе 1

- Каркас FastAPI-приложения.
- Заготовка aiogram-бота.
- Конфигурация через переменные окружения.
- Structured logging в JSON-формате.
- Healthcheck: `GET /health`.
- Readiness check: `GET /ready`.
- Telegram webhook endpoint: `POST /telegram/webhook/{secret}`.
- Docker Compose для backend, PostgreSQL и Redis.
- `.env.example` с финальными MVP-параметрами.

## MVP-настройки

- Доступ: приватный бот, только Telegram ID из `ALLOWED_TELEGRAM_IDS`.
- Рабочие дни: понедельник-пятница.
- Рабочие часы: `10:00-19:00`, UTC+3 / Europe/Moscow.
- Длительность встречи: строго 30 минут.
- Минимальное время до встречи: 2 часа.
- Горизонт бронирования: 14 дней.
- Буфер между встречами: 0 минут.
- Pending-заявка: 15 минут, временная бронь в Redis.
- Google Meet: создавать автоматически.
- Google Calendar: выделенный календарь через Service Account.

## Локальный запуск через Docker Compose

1. Скопируйте переменные окружения:

```bash
cp .env.example .env
```

2. Заполните в `.env` реальные значения:

- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_WEBHOOK_SECRET`;
- `ADMIN_TELEGRAM_IDS`;
- `ALLOWED_TELEGRAM_IDS`;
- `GOOGLE_CALENDAR_ID`;
- `GOOGLE_SERVICE_ACCOUNT_FILE` или `GOOGLE_SERVICE_ACCOUNT_JSON`.

3. Запустите сервисы:

```bash
docker compose up --build
```

4. Примените миграции БД:

```bash
docker compose exec backend alembic upgrade head
```

5. Проверьте приложение:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Локальный запуск без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn bot_helper.main:app --reload
```

Для запуска без Docker PostgreSQL и Redis должны быть доступны по адресам из `.env`.

Миграции без Docker:

```bash
alembic upgrade head
```

## Логи

Приложение пишет structured logs в stdout. В логах должны быть:

- `timestamp`;
- `level`;
- `event`;
- `component`;
- `request_id`, если событие связано с HTTP-запросом;
- технические детали без секретов.

В логи нельзя писать:

- Telegram bot token;
- Google service account JSON;
- Google private key;
- access/refresh tokens;
- полный email и полное описание встречи.

## Webhook для разработки

На этапе разработки webhook можно открыть через локальный туннель. URL будет вида:

```text
https://<tunnel-domain>/telegram/webhook/<TELEGRAM_WEBHOOK_SECRET>
```

Регистрация webhook будет добавлена на следующих этапах вместе с полноценной Telegram-интеграцией.
