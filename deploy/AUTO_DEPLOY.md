# Автодеплой после push в GitHub

Цель: после каждого `git push` в ветку `main` GitHub Actions запускает тесты, подключается к серверу по SSH, подтягивает свежий код, пересобирает backend-контейнер, применяет миграции, проверяет `/health` и `/ready`, затем регистрирует Telegram webhook на домен.

## Алгоритм

1. Вы отправляете код в GitHub в ветку `main`.
2. GitHub Actions запускает workflow `Test and deploy`.
3. Job `Run tests`:
   - ставит Python 3.12;
   - устанавливает проект с dev-зависимостями;
   - запускает `python -m pytest -q`.
4. Если тесты прошли, job `Deploy to production`:
   - подключается к серверу по SSH;
   - переходит в папку проекта;
   - делает `git fetch origin main`;
   - делает `git merge --ff-only origin/main`;
   - запускает `deploy/remote_deploy.sh`.
5. Серверный скрипт:
   - останавливается, если на сервере есть незакоммиченные изменения;
   - проверяет, что сервер оказался ровно на коммите из GitHub Actions;
   - выполняет `docker compose -f docker-compose.prod.yml up -d --build backend`;
   - применяет `alembic upgrade head`;
   - ждет healthy-статус backend;
   - проверяет `https://calendar.treeboxfree.ru/health`;
   - проверяет `https://calendar.treeboxfree.ru/ready`;
   - заново регистрирует Telegram webhook.

## Что уже сделано в репозитории

- `.github/workflows/deploy.yml` - GitHub Actions workflow.
- `deploy/remote_deploy.sh` - скрипт, который выполняется на сервере.

## Что нужно настроить вручную в GitHub

Откройте репозиторий GitHub:

`Settings -> Secrets and variables -> Actions -> New repository secret`

Добавьте секреты:

| Secret | Значение |
| --- | --- |
| `DEPLOY_HOST` | `132.243.23.203` |
| `DEPLOY_PORT` | `22` |
| `DEPLOY_USER` | `root` |
| `DEPLOY_PATH` | `/opt/telegram-calendar-bot` |
| `APP_BASE_URL` | `https://calendar.treeboxfree.ru` |
| `DEPLOY_SSH_PRIVATE_KEY` | приватный SSH-ключ для доступа к серверу |

## Как подготовить SSH-ключ

Для текущего проекта ключ уже создан на этом Mac:

```text
Приватный ключ: ~/.ssh/telegram_calendar_deploy
Публичный ключ: ~/.ssh/telegram_calendar_deploy.pub
```

Публичная часть уже добавлена на сервер в `/root/.ssh/authorized_keys`.

Если когда-нибудь нужно будет создать ключ заново, используйте:

На вашем Mac создайте отдельный ключ для деплоя:

```bash
ssh-keygen -t ed25519 -C "github-actions-telegram-calendar-bot" -f ~/.ssh/telegram_calendar_deploy
```

Скопируйте публичный ключ на сервер:

```bash
ssh-copy-id -i ~/.ssh/telegram_calendar_deploy.pub root@132.243.23.203
```

Если `ssh-copy-id` недоступен, выполните:

```bash
cat ~/.ssh/telegram_calendar_deploy.pub
```

Затем на сервере добавьте эту строку в файл:

```text
/root/.ssh/authorized_keys
```

В GitHub secret `DEPLOY_SSH_PRIVATE_KEY` вставьте содержимое приватного ключа:

```bash
cat ~/.ssh/telegram_calendar_deploy
```

Важно: вставляется именно приватный ключ, включая строки `BEGIN OPENSSH PRIVATE KEY` и `END OPENSSH PRIVATE KEY`.

## Как включить ручное подтверждение деплоя

Это необязательно, но полезно.

1. В GitHub откройте `Settings -> Environments`.
2. Создайте environment `production`.
3. Включите `Required reviewers`, если хотите подтверждать деплой вручную.

Workflow уже использует `environment: production`, поэтому GitHub подхватит эти правила автоматически.

Пока secrets не добавлены, workflow не будет падать: тесты пройдут, а deploy-шаг будет аккуратно пропущен с сообщением `Deploy secrets are not configured yet`.

## Как проверить, что автодеплой работает

1. Сделайте маленький commit.
2. Выполните:

```bash
git push origin main
```

3. В GitHub откройте вкладку `Actions`.
4. Откройте workflow `Test and deploy`.
5. Дождитесь зеленых галочек у jobs `Run tests` и `Deploy to production`.
6. Проверьте домен:

```bash
curl -fsS https://calendar.treeboxfree.ru/health
curl -fsS https://calendar.treeboxfree.ru/ready
```

7. Проверьте webhook:

```bash
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

В `url` должен быть адрес:

```text
https://calendar.treeboxfree.ru/telegram/webhook/<secret>
```

## Если деплой остановился

Частые причины:

- тесты не прошли;
- GitHub secret указан неверно;
- сервер недоступен по SSH;
- на сервере есть незакоммиченные изменения в `/opt/telegram-calendar-bot`;
- контейнер backend не стал healthy;
- `/ready` вернул ошибку из-за PostgreSQL, Redis, Telegram или Google Calendar настроек.

Смотреть причину нужно в GitHub: `Actions -> Test and deploy -> failed job`.
