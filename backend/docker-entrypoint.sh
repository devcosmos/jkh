#!/bin/sh
# Раньше backend-контейнер сразу стартовал uvicorn без миграций — на чистой БД /health/ready
# и все остальные эндпоинты падали, пока кто-то не зайдёт в контейнер и не накатит их
# вручную (см. backend/README.md, «Локальный запуск» — единая последовательность запуска).
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
