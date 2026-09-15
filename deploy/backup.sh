#!/usr/bin/env bash
set -euo pipefail

# Бэкап БД Postgres из контейнера `db` (docker-compose.yml) — раздел 12 ТЗ, RTO <= 4 часа.
# Формат pg_dump -Fc (custom) — сжатый, восстанавливается pg_restore (см. restore.sh),
# не зависит от версии psql на хосте.
#
# Использование: deploy/backup.sh [каталог-с-docker-compose.yml]
# По умолчанию каталог — корень репозитория (родитель deploy/).
# Переменные окружения:
#   JKH_BACKUP_DIR             — куда класть дампы (по умолчанию <compose-dir>/backups)
#   JKH_BACKUP_RETENTION_DAYS  — сколько дней хранить дампы (по умолчанию 14)
#
# Cron (на VPS, от пользователя с доступом к docker):
#   0 3 * * * /opt/jkh/deploy/backup.sh >> /var/log/jkh-backup.log 2>&1

COMPOSE_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${JKH_BACKUP_DIR:-$COMPOSE_DIR/backups}"
RETENTION_DAYS="${JKH_BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
out_file="$BACKUP_DIR/jkh_${timestamp}.dump"
tmp_file="${out_file}.part"

cd "$COMPOSE_DIR"
docker compose exec -T db pg_dump -U jkh -Fc jkh > "$tmp_file"
mv "$tmp_file" "$out_file"

size=$(du -h "$out_file" | cut -f1)
echo "backup saved: $out_file ($size)"

# Ротация: хранить только дампы младше RETENTION_DAYS дней.
find "$BACKUP_DIR" -maxdepth 1 -name 'jkh_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete

echo "retention: keeping dumps from the last ${RETENTION_DAYS} days in $BACKUP_DIR"
