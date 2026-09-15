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

## Тесты

Требуют реальный Postgres (модели используют Enum/JSON-типы, несовместимые со SQLite) —
поднимается отдельным одноразовым контейнером, не тем же, что дев-стек:

```bash
docker run -d --name jkh_test_db -e POSTGRES_USER=jkh -e POSTGRES_PASSWORD=jkh \
  -e POSTGRES_DB=jkh_test -p 55432:5432 postgres:16

cd /Users/cosmos/Documents/github/JKH
python3 -m venv .venv-backend && source .venv-backend/bin/activate
pip install -r backend/requirements-dev.txt
cd backend && python3 -m pytest tests/ -v
```

Схема создаётся тестами напрямую через `Base.metadata.create_all` (не через alembic —
быстрее, и тестируется бизнес-логика моделей/API, а не сами миграции). Таблицы полностью
очищаются между тестами (`TRUNCATE ... CASCADE`), сессия БД в тесте — та же, что видит
FastAPI-эндпоинт (переопределение `get_db` в `tests/conftest.py`), поэтому `db_session`
можно использовать и для подготовки данных, и для проверки того, что записал эндпоинт.

Покрыто: переходы статусов заявки (`test_maintenance_requests.py`, включая запрещённые
переходы и терминальные статусы), решения диспетчера по риск-кейсу
(`test_risk_case_decisions.py`), автосоздание черновика заявки и его дедупликация
(`test_auto_draft_request.py`), логин/RBAC (`test_auth.py`). Границы эпизода и правило
флаппинга (`scripts/build_episodes.py`) покрыты отдельно, в основном `.venv` репозитория:
`python3 -m pytest scripts/tests/ -v` (не требует Postgres, только DuckDB).

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
- Фоновый worker поднят (`app/workers/replay_worker.py`) — replay истории + живой инференс,
  курсор возобновления в `replay_state`.
- Автоматическое создание черновика заявки по правилу (раздел 10 плана) —
  `maybe_create_draft_request` в `replay_worker.py`, срабатывает при открытии нового
  риск-кейса (не на повторном расчёте на уже открытом), шаблон вида работ по типу датчика,
  дедуп по (устройство, вид работы, активный риск-кейс). Покрыто тестами, см. «Тесты» выше.
- Тесты: переходы статусов, RBAC, автосоздание заявки, границы эпизода/флаппинг — см. «Тесты».
- `POST /auth/change-password` — смена собственного пароля (требует текущий пароль, не
  только валидный токен). Раньше пароль менялся только вручную в БД.
- Соответствие канал→устройство (раздел 7.3/докстринг `entities.py` — раньше `devices`
  была пустой таблицей): `scripts/link_channels_to_devices.py`, эвристика по имени канала
  («В8 ПК96» → устройство «В8-ПК96»), 87.8% покрытия насос/вентилятор (469 из 534),
  идемпотентно. Не даёт новых ML-признаков (управляющий переключатель — не независимое
  измерение), но даёт реальную идентичность устройства в заявках вместо голого ID канала.
- Минимальная матрица доступа по объектам (раздел 12 плана — полная версия с
  подразделениями прямо отмечена в плане как требование будущего пилота, не MVP):
  таблица `user_object_access` + `POST/DELETE/GET /access/users/{id}/objects` (только
  admin). Если пользователю не назначено ни одного объекта — ограничение не действует
  (сознательное упрощение, чтобы не сломать пользователей без настроенного доступа).
  Действует на `GET/POST /risk-cases`, `POST /risk-cases/{id}/decisions`,
  `GET /maintenance-requests`, `POST /maintenance-requests/{id}/transitions|approve`,
  `GET /predictions` — везде, где запись привязана к объекту через канал.

## Не реализовано в этом проходе (открыто, зафиксировано честно)

- Импорт данных из CSV/эпизодов/прогнозов в эти таблицы — только схема, наполнение будет
  отдельным CLI-скриптом (`scripts/`) поверх уже готового `scripts/build_episodes.py` и
  `scripts/train_model.py`.
- Полная матрица доступа с подразделениями (не только объектами) — по плану это требование
  будущего пилота, не MVP; сейчас реализована только объектная часть (см. выше).
- PostGIS/геометрия — намеренно упрощено до nullable WKT-текста (см. докстринг
  `entities.py`), т.к. в справочнике объектов пока нет ни одной координаты.
- Нет POST-эндпоинта для ручного создания заявки — по разделу 10 плана создание только
  автоматическое по правилу; ручное создание не требуется контрактом раздела 11.
