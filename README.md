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
backend/             FastAPI-приложение
  app/
    api/              HTTP, валидация, проверка доступа
    services/         риски, решения, заявки, аналитика
    ml/               контракт признаков, загрузка моделей, объяснения (SHAP) —
                       рантайм-код, вызывается worker'ом
    workers/           доставка событий (replay) и запуск расчётов — тонкий,
                       вызывает app/ml/
    models/, schemas/  ORM-модели и контракты API
  migrations/          Alembic
  tests/

frontend/
  src/
    features/          risks/, requests/ — первые два раздела, вынесенные из pages/
                        (остальные 8 пока там же — разбираются постепенно)
    pages/              остальные разделы интерфейса
    components/         действительно общие компоненты
    api/

ml/                    офлайн-код обучения/оценки — НЕ импортируется рантаймом backend
  features/             build_features*.py, build_replay_feed.py, build_episodes.py
  training/             train_model*.py, train_anomaly_model.py
  evaluation/           evaluate_episodes*.py, compute_calibration.py
  experiments/          альтернативные/непроизводственные варианты (daily, газ_numeric)
  tests/

scripts/
  data/                 import_analysis_to_db.py, link_channels_to_devices.py,
                        profile_data.py, manifest.py
  maintenance/          backfill_*.py, register_model_version.py,
                        check_worker_feature_parity.py
  demo/                 seed_maintenance_request*.py — явно демонстрационные
  tests/

artifacts/             модели (.cbm/.joblib), витрины (features_*.parquet),
                        replay_feed_*.parquet, отчёты (model_report_*.json/.md),
                        episode_evaluation_*.json, calibration_*.json — заменяет
                        прежние data/ и docs/documentation/analysis/; шесть файлов
                        демокомплекта worker'а отслеживаются в Git, остальное — нет
                        (см. .gitignore)

dataset/               Исходные журналы событий и справочники (локально, не в Git)
deploy/                Docker Compose для прод-сервера, Caddy, backup/restore
docs/                  Документация проекта — см. docs/documentation/README.md
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
«Первый пользователь» в `backend/README.md` и `scripts/data/import_analysis_to_db.py` для
наполнения демо-данными (риск-кейсы, прогнозы, версии моделей).

**Наполнение демо-данными требует закрытого датасета.** `scripts/data/import_analysis_to_db.py`
читает не только `artifacts/` (частично в Git — демокомплект из 6 файлов моделей/фидов), но
и `dataset/справочник_объектов_диспетчер.csv` + `dataset/справочник_каналов_датчиков.csv`
(объекты/каналы) и `artifacts/episodes_*.parquet` + `artifacts/scored_*.parquet` (регенерируемые
обучающие артефакты) — ни то, ни другое не в Git (раздел ТЗ «закрытые данные», см. корневой
`.gitignore`). Без доступа к исходному датасету импорт не запустится: backend/worker поднимутся
и будут технически исправны (миграции, health-checks, worker переиграет фид и посчитает
прогнозы), но без `channels`/`objects` в БД `RiskCase` создать не из чего — worker'у попросту
негде взять список каналов. Проверено на чистом окружении (изолированный Docker-стек, новые
volumes) 22 сентября 2026: с доступом к `dataset/` полная последовательность миграции →
администратор → импорт → worker → риск-кейс → решение диспетчера → заявка проходит без правок
кода (OPS-01, см. `analys_and_todo.md`).

## Тесты

- Backend: `cd backend && python3 -m pytest tests/ -v` (нужен отдельный тестовый Postgres —
  см. `backend/README.md`, раздел «Тесты»).
- Обработка эпизодов/флаппинга: `python3 -m pytest ml/tests/ -v` (только DuckDB, без
  Postgres).
- Служебные скрипты (регистрация версии модели): `python3 -m pytest scripts/tests/ -v`.
- Frontend: `cd frontend && npx tsc -b && npm run build` (типы и прод-сборка).
- E2E (Playwright): вход, риск → решение диспетчера → заявка, запрет доступа к чужому
  объекту — на синтетических фикстурах, не на закрытом датасете. Не поднимает стек сам —
  см. `frontend/e2e/README.md`.

## Документация

Подробное устройство системы, аудит данных, политика разметки, протокол проверок и отчёты
моделей — [docs/documentation/](docs/documentation/README.md). Матрица соответствия
требованиям и сопроводительная документация для сдачи — [docs/deliverables/](docs/deliverables/README.md).

## Прод-развёртывание

См. [deploy/README.md](deploy/README.md) — требования к серверу, первоначальная настройка,
Docker Compose + Caddy (TLS), backup/restore.
