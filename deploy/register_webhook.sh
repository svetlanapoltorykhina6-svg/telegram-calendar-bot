#!/usr/bin/env sh
set -eu

if [ ! -f ".env" ]; then
  echo "ERROR: .env not found. Run this script from the project directory." >&2
  exit 1
fi

set -a
. ./.env
set +a

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN is empty." >&2
  exit 1
fi

if [ -z "${APP_BASE_URL:-}" ]; then
  echo "ERROR: APP_BASE_URL is empty." >&2
  exit 1
fi

if [ -z "${TELEGRAM_WEBHOOK_SECRET:-}" ]; then
  echo "ERROR: TELEGRAM_WEBHOOK_SECRET is empty." >&2
  exit 1
fi

WEBHOOK_URL="${APP_BASE_URL%/}/telegram/webhook/${TELEGRAM_WEBHOOK_SECRET}"

echo "Registering Telegram webhook: ${APP_BASE_URL%/}/telegram/webhook/<hidden>"
curl -fsS \
  --data-urlencode "url=${WEBHOOK_URL}" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook"
echo
