from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.schemas import HealthOut

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=HealthOut,
    summary="Проверить работу сервиса",
    description="Без авторизации. Возвращает status: ok, если приложение отвечает.",
)
def live() -> dict:
    return {"status": "ok"}


@router.get(
    "/ready",
    response_model=HealthOut,
    summary="Проверить подключение к БД",
    description="Без авторизации. Выполняет проверочный запрос к базе данных и при успехе возвращает status: ok.",
)
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
