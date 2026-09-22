# ЖКХ «Город 8» — прогнозирование «Отказ датчика»

Система поддержки решений диспетчера ЖКХ: по потоку событий датчиков (насос/вентилятор,
дым/газ) предсказывает риск отказа канала, показывает объяснение прогноза и позволяет
диспетчеру принять решение (наблюдать / направить на проверку / отклонить) с созданием
заявки на обслуживание. Два трека оцениваются независимо друг от друга.

## Стек

FastAPI + PostgreSQL + Alembic (backend), React + TypeScript (frontend), фоновый Python
worker (replay истории + живой инференс CatBoost), Docker Compose.

## Структура репозитория

```
backend/     FastAPI-приложение, ORM-модели, миграции, worker, тесты
frontend/    React-интерфейс диспетчера и администратора
scripts/     Подготовка данных, обучение моделей, импорт, служебные и демо-скрипты
dataset/     Исходные журналы событий и справочники (локально, не в Git)
data/        Модели и replay-файлы, которые читает worker
deploy/      Docker Compose для прод-сервера, Caddy, backup/restore
docs/        Документация проекта — см. docs/documentation/README.md
```

## Быстрый старт (локальная разработка)

```bash
git clone <репозиторий> jkh && cd jkh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

Дальше backend и frontend поднимаются раздельно для разработки с hot-reload — см.
[backend/README.md](backend/README.md) (включая первого пользователя и тесты) и
[frontend/README.md](frontend/README.md).

Поднять весь стек в контейнерах разом (без hot-reload, ближе к проду):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Backend — `localhost:8000` (`/api/docs` — Swagger), frontend — `localhost:5174`, Postgres —
`localhost:5433`. После первого подъёма нужны миграции, первый пользователь и данные — см.
«Первый пользователь» в `backend/README.md` и `scripts/import_analysis_to_db.py` для
наполнения демо-данными (риск-кейсы, прогнозы, версии моделей) из уже посчитанных
артефактов в `artifacts/`.

## Тесты

- Backend: `cd backend && python3 -m pytest tests/ -v` (нужен отдельный тестовый Postgres —
  см. `backend/README.md`, раздел «Тесты»).
- Обработка эпизодов/флаппинга: `python3 -m pytest scripts/tests/ -v` (только DuckDB, без
  Postgres).
- Frontend: `cd frontend && npx tsc -b && npm run build` (типы и прод-сборка; e2e-тестов
  пользовательских сценариев пока нет).

## Документация

Подробное устройство системы, аудит данных, политика разметки, протокол проверок и отчёты
моделей — [docs/documentation/](docs/documentation/README.md). Матрица соответствия
требованиям и сопроводительная документация для сдачи — [docs/deliverables/](docs/deliverables/README.md).

## Прод-развёртывание

См. [deploy/README.md](deploy/README.md) — требования к серверу, первоначальная настройка,
Docker Compose + Caddy (TLS), backup/restore.
