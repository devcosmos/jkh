import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, Prediction, User
from app.schemas.schemas import PredictionOut

router = APIRouter(prefix="/predictions", tags=["predictions"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PredictionOut])
def list_predictions(
    channel_id: int | None = None,
    category: str | None = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Prediction]:
    """Журнал прогнозов — неизменяемые записи (раздел 9.2 плана: «Журнал прогнозов»).

    `category` различает независимо оцениваемые треки (тема 18 CSV с ответами
    организаторов) — sensor_failure_pump_fan / sensor_failure_smoke_gas."""
    stmt = select(Prediction)
    if channel_id is not None:
        stmt = stmt.where(Prediction.channel_id == channel_id)
    if category is not None:
        stmt = stmt.where(Prediction.category == category)
    if since is not None:
        stmt = stmt.where(Prediction.created_at >= since)
    if until is not None:
        stmt = stmt.where(Prediction.created_at <= until)
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = stmt.join(Channel, Channel.id == Prediction.channel_id).where(
            Channel.object_id.in_(accessible)
        )
    stmt = stmt.order_by(Prediction.created_at.desc())
    return list(db.scalars(stmt.offset(offset).limit(limit)))
