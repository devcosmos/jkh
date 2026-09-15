import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.entities import Prediction
from app.schemas.schemas import PredictionOut

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PredictionOut])
def list_predictions(
    channel_id: int | None = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[Prediction]:
    """Журнал прогнозов — неизменяемые записи (раздел 9.2 плана: «Журнал прогнозов»)."""
    stmt = select(Prediction)
    if channel_id is not None:
        stmt = stmt.where(Prediction.channel_id == channel_id)
    if since is not None:
        stmt = stmt.where(Prediction.created_at >= since)
    if until is not None:
        stmt = stmt.where(Prediction.created_at <= until)
    stmt = stmt.order_by(Prediction.created_at.desc())
    return list(db.scalars(stmt.offset(offset).limit(limit)))
