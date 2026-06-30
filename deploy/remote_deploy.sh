#!/usr/bin/env sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BRANCH="${DEPLOY_BRANCH:-main}"
EXPECTED_COMMIT="${DEPLOY_COMMIT:-}"
HEALTH_URL="${HEALTH_URL:-}"
READY_URL="${READY_URL:-}"
REGISTER_WEBHOOK="${REGISTER_WEBHOOK:-true}"

log() {
  printf '%s\n' "==> $*"
}

require_file() {
  if [ ! -f "$1" ]; then
    printf '%s\n' "ERROR: required file not found: $1" >&2
    exit 1
  fi
}

require_file ".env"
require_file "$COMPOSE_FILE"

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
  printf '%s\n' "ERROR: expected branch $BRANCH, got $CURRENT_BRANCH" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  printf '%s\n' "ERROR: server working tree has uncommitted changes. Deploy stopped." >&2
  git status --short >&2
  exit 1
fi

if [ -n "$EXPECTED_COMMIT" ]; then
  CURRENT_COMMIT="$(git rev-parse HEAD)"
  if [ "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]; then
    printf '%s\n' "ERROR: expected commit $EXPECTED_COMMIT, got $CURRENT_COMMIT" >&2
    exit 1
  fi
fi

log "Building and starting production containers"
docker compose -f "$COMPOSE_FILE" up -d --build backend

log "Running database migrations"
docker compose -f "$COMPOSE_FILE" exec -T backend alembic upgrade head

log "Waiting for backend healthcheck"
attempt=1
while [ "$attempt" -le 30 ]; do
  status="$(docker compose -f "$COMPOSE_FILE" ps --format json backend | grep -o '"Health":"[^"]*"' | head -1 | cut -d '"' -f 4 || true)"
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 2
  attempt=$((attempt + 1))
done

if [ "$attempt" -gt 30 ]; then
  printf '%s\n' "ERROR: backend did not become healthy." >&2
  docker compose -f "$COMPOSE_FILE" ps >&2
  docker compose -f "$COMPOSE_FILE" logs --tail=120 backend >&2
  exit 1
fi

if [ -n "$HEALTH_URL" ]; then
  log "Checking $HEALTH_URL"
  curl -fsS "$HEALTH_URL" >/dev/null
fi

if [ -n "$READY_URL" ]; then
  log "Checking $READY_URL"
  curl -fsS "$READY_URL" >/dev/null
fi

if [ "$REGISTER_WEBHOOK" = "true" ]; then
  log "Registering Telegram webhook"
  sh deploy/register_webhook.sh >/dev/null
fi

log "Deploy completed"
git rev-parse --short HEAD
docker compose -f "$COMPOSE_FILE" ps
