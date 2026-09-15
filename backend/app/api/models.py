from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.entities import ModelVersion
from app.schemas.schemas import ModelVersionOut

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(get_current_user)])


@router.get("/current", response_model=ModelVersionOut)
def current_model(db: Session = Depends(get_db)) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    if mv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Активная версия модели не назначена")
    return mv
