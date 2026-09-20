from fastapi import APIRouter, FastAPI

from app.api import (
    access,
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
    description="Прототип: категория «Отказ датчика». См. docs/Рабочее_ТЗ_MVP.md.",
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

app.include_router(api)
