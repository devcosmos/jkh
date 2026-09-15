# Backend — прогнозирование «Отказ датчика»

FastAPI + PostgreSQL + Alembic. Схема — `app/models/entities.py`, упрощения для MVP описаны
в докстринге файла. Обязательный API-контур на сегодня: объекты, риски/решения, журнал
прогнозов, заявки, health — см. `app/main.py`.

## Локальный запуск

Порт Postgres на хосте — **5433** (не 5432 — тот занят контейнером другого проекта,
`priem-chat-db`). Внутри docker-сети контейнеры общаются по стандартному 5432.

```bash
cd /Users/cosmos/Documents/github/JKH
docker compose up -d db
cd backend
source ../.venv/bin/activate   # корневой venv репозитория (duckdb/catboost/...)
pip install -r requirements.txt
export JKH_DATABASE_URL="postgresql+psycopg://jkh:jkh@localhost:5433/jkh"
alembic upgrade head            # миграция уже в репозитории (migrations/versions/634798e9a87c_init.py)
uvicorn app.main:app --reload
```

При запуске через `docker compose up -d backend` (весь стек в контейнерах, не только БД)
переменная `JKH_DATABASE_URL` уже прописана в `docker-compose.yml` и указывает на `db:5432`
(внутренний DNS докера) — экспортировать её вручную не нужно.

Открыть `http://localhost:8000/docs` — интерактивная OpenAPI-документация (требование
раздела 11 плана реализации).

## Первый пользователь

Таблица `users` пуста после миграции. Создать администратора:

```bash
python3 -c "
from app.core.db import SessionLocal
from app.models.entities import User
from app.models.enums import UserRole
from app.core.security import hash_password
db = SessionLocal()
db.add(User(username='admin', password_hash=hash_password('CHANGE-ME'), role=UserRole.admin))
db.commit()
"
```

Затем `POST /auth/login` (form-data: `username`, `password`) вернёт JWT для `Authorization:
Bearer <token>`.

## Что уже сделано (15 сентября 2026)

- Полная ORM-схема по разделу 7.3 плана: объекты, каналы, устройства, эпизоды, версии
  моделей, прогнозы, риск-кейсы, решения, заявки, аудит, импорт-раны, пользователи.
- Локальная аутентификация (JWT) и проверка роли на backend (раздел 12 ТЗ).
- Обязательные MVP-эндпоинты (раздел 2 ТЗ): `/objects`, `/objects/geojson`,
  `/channels/{id}`, `/channels/{id}/episodes`, `/risk-cases`,
  `/risk-cases/{id}/decisions`, `/predictions`, `/maintenance-requests` (+`approve`,
  `transitions`), `/models/current`, `/health/live`, `/health/ready`.
- Жизненный цикл заявки `draft→approved→in_progress→completed` (+`rejected`,`cancelled`)
  с проверкой разрешённых переходов (раздел 10 плана).
- Аудит изменений статусов риск-кейсов и заявок (`audit_log`).
- Первая миграция сгенерирована и применена на реальном Postgres 16 (`docker compose up -d db`,
  порт на хосте — 5433, т.к. 5432 занят другим проектом). Сквозной сценарий проверен:
  `/health/ready` бьёт в реальную БД, `/auth/login` выдаёт JWT, защищённые эндпоинты отдают
  401 без токена и 200 с ним.
- Зависимости обновлены под Python 3.14: старые пины `fastapi`/`pydantic`/`sqlalchemy`/
  `alembic` не собирались или падали на 3.14, подняты до актуальных версий (см.
  `requirements.txt`). `passlib` заменён на прямой вызов `bcrypt` — `passlib` 1.7.4
  несовместим с `bcrypt` 4.x (не читает версию бэкенда).

## Не реализовано в этом проходе (открыто, зафиксировано честно)

- Импорт данных из CSV/эпизодов/прогнозов в эти таблицы — только схема, наполнение будет
  отдельным CLI-скриптом (`scripts/`) поверх уже готового `scripts/build_episodes.py` и
  `scripts/train_model.py`.
- Автоматическое создание черновика заявки по правилу (раздел 10 плана) — сейчас заявки
  можно только читать/утверждать/переводить по статусам, создание вручную не реализовано.
- Фоновый worker (раздел 3 ТЗ MVP) — не поднят, инференс модели по расписанию отсутствует.
- RBAC ограничен тремя ролями без детальной матрицы «объект/подразделение» из раздела 12
  плана — сейчас проверка только на уровне роли, не на уровне доступных объектов.
- PostGIS/геометрия — намеренно упрощено до nullable WKT-текста (см. докстринг
  `entities.py`), т.к. в справочнике объектов пока нет ни одной координаты.
