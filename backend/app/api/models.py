from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.entities import ModelVersion, User
from app.models.enums import UserRole
from app.schemas.schemas import ModelVersionOut

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(get_current_user)])


@router.get(
    "/current",
    response_model=list[ModelVersionOut],
    summary="Получить активные модели",
    description="Активные версии моделей, типы датчиков, даты обучения, пороги и метрики качества.",
    responses={
        401: {
            "description": "Требуется вход или токен недействителен",
        },
    },
)
def current_models(db: Session = Depends(get_db)) -> list[ModelVersion]:
    """Активные версии модели — по одной на независимо оцениваемый трек (насос/вентилятор,
    дым/газ — тема 18 CSV с ответами: «два независимых результата, оцениваются отдельно»),
    поэтому активных версий может быть несколько одновременно."""
    return list(db.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))))


@router.get(
    "",
    response_model=list[ModelVersionOut],
    summary="Получить историю версий моделей",
    description=(
        "Все версии, включая замещённые дообучением (раздел 8 ЖКХ.md: «модуль дообучения "
        "прогнозных моделей на новых данных» — регистрация новой версии описана в "
        "scripts/register_model_version.py). Только администратор."
    ),
    responses={
        401: {"description": "Требуется вход или токен недействителен"},
        403: {"description": "Недостаточно прав"},
    },
)
def model_history(
    db: Session = Depends(get_db), admin: User = Depends(require_role(UserRole.admin))
) -> list[ModelVersion]:
    return list(db.scalars(select(ModelVersion).order_by(ModelVersion.trained_at.desc())))
