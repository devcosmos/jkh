#!/usr/bin/env bash
set -euo pipefail

# Восстановление БД Postgres из дампа, снятого backup.sh. ДЕСТРУКТИВНО — перезаписывает
# текущие данные в БД `jkh`. Раздел 12 ТЗ: цель <= 4 часов на восстановление (сама операция
# занимает минуты — см. deploy/README.md, раздел «Backup/restore», для измеренного времени).
#
# Использование: deploy/restore.sh <путь-к-дампу> [каталог-с-docker-compose.yml]

DUMP_FILE="${1:?Использование: restore.sh <путь-к-дампу> [compose-dir]}"
COMPOSE_DIR="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "дамп не найден: $DUMP_FILE" >&2
  exit 1
fi

cd "$COMPOSE_DIR"

if [ -t 0 ]; then
  read -r -p "Это ПЕРЕЗАПИШЕТ текущую БД данными из $DUMP_FILE. Продолжить? [yes/N] " confirm
  if [ "$confirm" != "yes" ]; then
    echo "отменено"
    exit 1
  fi
fi

echo "останавливаю backend и worker (чтобы не писали поверх восстановления)..."
docker compose stop backend worker 2>/dev/null || true

echo "восстанавливаю дамп (pg_restore --clean --if-exists)..."
docker compose exec -T db pg_restore -U jkh -d jkh --clean --if-exists --no-owner < "$DUMP_FILE"

echo "запускаю backend и worker обратно..."
docker compose start backend worker 2>/dev/null || true

echo "готово. Проверить: curl -f https://<домен>/api/health/ready"
