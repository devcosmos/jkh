#!/usr/bin/env bash
# Автодеплой на VPS по опросу (poll), не webhook: не требует открытия дополнительного
# порта/секретов GitHub Actions для SSH — достаточно read-only deploy key, уже настроенного
# на сервере (см. deploy/README.md, раздел «Автодеплой»). Запускается по cron, не демон.
#
# Логика: если origin/main ушёл вперёд текущего HEAD — обновить код, пересобрать только то,
# что реально изменилось (docker compose build сам пропускает не изменившиеся слои/сервисы),
# прогнать миграции, поднять стек. Если новых коммитов нет — ничего не делать (никаких
# рестартов контейнеров без необходимости).
set -euo pipefail

cd "$(dirname "$0")/.."
LOG="/opt/jkh/deploy/auto_deploy.log"
exec >> "$LOG" 2>&1

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "up to date ($LOCAL), nothing to do"
  exit 0
fi

echo "new commits: $LOCAL -> $REMOTE"
git log --oneline "$LOCAL..$REMOTE"

# .env и artifacts/*.parquet,*.cbm,*.joblib не в git (см. .gitignore) — reset --hard их не
# трогает, т.к. git не отслеживает эти пути вообще (не просто игнорирует незакоммиченные
# изменения — путь никогда не был в индексе). Демокомплект (6 файлов) отслеживается и придёт
# через git pull как обычно.
git reset --hard origin/main

docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml build
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
docker compose exec -T backend alembic upgrade head

echo "deployed $REMOTE"
