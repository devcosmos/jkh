from fastapi import APIRouter, FastAPI

from app.api import (
    access,
    analytics,
    audit,
    auth,
    channels,
    dashboard,
    health,
    maintenance_requests,
    models,
    objects,
    predictions,
    risks,
)

app = FastAPI(
    title="ЖКХ — прогнозирование отказов датчиков",
    version="0.1.0",
    description="""
API сервиса прогнозирования отказов датчиков: объекты и каналы, прогнозы,
риск-кейсы, решения и заявки на обслуживание.

### Авторизация
Нажмите **Authorize** и введите логин и пароль своей учётной записи.
Swagger получит JWT через `POST /api/auth/login` и будет отправлять его
в заголовке `Authorization: Bearer <access_token>`.
При интеграции передавайте `username` и `password` как
`application/x-www-form-urlencoded`. Проверки `/api/health/*` доступны без токена.

### Работа с данными
Списки используют `limit` (размер страницы) и `offset` (число пропущенных записей).
Списки каналов, рисков, прогнозов, заявок и аудита возвращают общее число
записей с учётом фильтров в заголовке `X-Total-Count`.
Вероятности передаются числами от 0 до 1; даты — в формате ISO 8601.
Категории: `sensor_failure_pump_fan` (насосы/вентиляторы) и
`sensor_failure_smoke_gas` (дым/газ).

### Ошибки и права
`401` — требуется вход или токен недействителен; `403` — недостаточно прав;
`404` — запись не найдена; `409` — конфликт данных или недопустимый переход статуса;
`422` — неверные параметры запроса. Подробности ошибки находятся в поле `detail`.
Управление пользователями и аудит доступны администратору;
смена статуса заявки — диспетчеру и администратору.
**Try it out / Execute выполняет настоящий запрос:** операции изменения сохраняют данные.
""",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1, "filter": True},
    openapi_tags=[
        {"name": "auth", "description": "Вход и смена собственного пароля."},
        {"name": "objects", "description": "Объекты и их иерархия."},
        {"name": "channels", "description": "Каналы датчиков, эпизоды неисправностей и динамика их частоты."},
        {"name": "risks", "description": "Риск-кейсы и решения по ним."},
        {"name": "predictions", "description": "Журнал прогнозов с вероятностями и объяснениями."},
        {"name": "maintenance", "description": "Заявки на обслуживание и переходы статусов."},
        {"name": "models", "description": "Активные версии моделей и метрики качества."},
        {"name": "dashboard", "description": "Сводные показатели системы."},
        {"name": "analytics", "description": "Расширенная аналитика: типы инцидентов, сезонность, отчёты по ремонтам (XLSX/PDF)."},
        {"name": "access", "description": "Пользователи и доступ к объектам. Только администратор."},
        {"name": "audit", "description": "Журнал изменений. Только администратор."},
        {"name": "health", "description": "Проверка работы сервиса и соединения с БД. Без авторизации."},
    ],
)

# Префикс /api нужен, чтобы Caddy на проде маршрутизировал по пути между этим backend
# и статикой frontend на одном домене без отдельного поддомена (см. deploy/Caddyfile).
api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(objects.router)
api.include_router(channels.router)
api.include_router(risks.router)
api.include_router(predictions.router)
api.include_router(maintenance_requests.router)
api.include_router(models.router)
api.include_router(access.router)
api.include_router(audit.router)
api.include_router(dashboard.router)
api.include_router(analytics.router)

app.include_router(api)
