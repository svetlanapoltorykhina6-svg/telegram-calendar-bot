# Deploy на сервер

Сервер для размещения: `132.243.23.203`.
Production-домен: `calendar.treeboxfree.ru`.

## Что нужно до запуска

1. Домен, направленный A-записью на `132.243.23.203`.
   Используем `calendar.treeboxfree.ru -> 132.243.23.203`.
2. SSH-доступ к серверу: пользователь, пароль или ключ.
3. Docker и Docker Compose plugin на сервере.
4. Файл `.env` на сервере, созданный из `.env.production.example`.
5. Папка `secrets/` на сервере с Google OAuth/Service Account файлами.

Без домена можно проверить `/health` по IP и порту, но Telegram webhook для рабочего режима требует HTTPS URL.

## Файлы

- `docker-compose.prod.yml` - production compose для backend, PostgreSQL, Redis и Caddy.
- `.env.production.example` - шаблон production переменных без секретов.
- `deploy/Caddyfile` - HTTPS reverse proxy.
- `deploy/register_webhook.sh` - регистрация Telegram webhook.
- `deploy/remote_deploy.sh` - серверный скрипт автодеплоя из GitHub Actions.
- `deploy/AUTO_DEPLOY.md` - инструкция по настройке автодеплоя после push в GitHub.

## Первый запуск

Команды выполняются из папки проекта на сервере.

```bash
cp .env.production.example .env
nano .env
mkdir -p secrets
```

В `.env` обязательно заполнить:

- `APP_BASE_URL=https://calendar.treeboxfree.ru`;
- `APP_DOMAIN=calendar.treeboxfree.ru`;
- `CADDY_EMAIL`;
- `POSTGRES_PASSWORD`;
- `DATABASE_URL` с тем же паролем PostgreSQL;
- `TELEGRAM_BOT_TOKEN`;
- `TELEGRAM_WEBHOOK_SECRET`;
- `ADMIN_TELEGRAM_IDS`;
- `ALLOWED_TELEGRAM_IDS`;
- `GOOGLE_CALENDAR_ID`;
- Google file paths/token settings.

Запуск:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

Проверка:

```bash
curl -fsS https://calendar.treeboxfree.ru/health
curl -fsS https://calendar.treeboxfree.ru/ready
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

Ожидаемо:

- `/health` возвращает `{"status":"ok"}`;
- `/ready` возвращает `status: ready`;
- в логах нет токенов, приватных ключей и полных персональных данных.

## Telegram webhook

После успешной проверки:

```bash
sh deploy/register_webhook.sh
```

Проверка webhook:

```bash
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

В ответе должен быть URL вида:

```text
https://calendar.treeboxfree.ru/telegram/webhook/<secret>
```

## Что проверяет разработчик

- контейнеры запущены;
- миграции применены;
- `/health` работает;
- `/ready` видит PostgreSQL, Redis, Telegram config и Google config;
- webhook зарегистрирован;
- в логах есть события запуска и healthcheck;
- секреты не попали в git.

## Что нужно проверить вручную

1. Написать боту `/start`.
2. Пройти сценарий создания заявки.
3. Нажать админское согласование.
4. Проверить, что событие появилось в Google Calendar.
5. Проверить, что email-приглашение и Google Meet появились в событии.
