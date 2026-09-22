# E2E (Playwright)

OPS-03 (`analys_and_todo.md`) — покрывает основной сценарий (вход → риск → решение диспетчера
→ заявка) и запрет доступа к чужому объекту. Не поднимает стек сам (см. `playwright.config.ts`)
— требует уже запущенных backend и frontend на отдельной БД с фикстурами.

## Запуск локально

```bash
# 1. Отдельная БД (не та, что использует основной демо-стек или pytest)
docker run -d --name jkh_e2e_db -e POSTGRES_USER=jkh -e POSTGRES_PASSWORD=jkh \
  -e POSTGRES_DB=jkh -p 55441:5432 postgres:16

# 2. Миграции + фикстуры
cd backend
export JKH_DATABASE_URL="postgresql+psycopg://jkh:jkh@localhost:55441/jkh"
alembic upgrade head
cd .. && python3 scripts/demo/seed_e2e_fixtures.py

# 3. Backend
cd backend && JKH_DATABASE_URL="postgresql+psycopg://jkh:jkh@localhost:55441/jkh" \
  uvicorn app.main:app --port 58020 &

# 4. Frontend (проксирует /api на шаг 3, не на обычный localhost:8000)
cd frontend && VITE_API_PROXY_TARGET=http://localhost:58020 npx vite --port 58030 &

# 5. Тесты
cd frontend && E2E_BASE_URL=http://localhost:58030 npx playwright test
```

`scripts/demo/seed_e2e_fixtures.py` идемпотентен — безопасно перезапускать на той же БД.
