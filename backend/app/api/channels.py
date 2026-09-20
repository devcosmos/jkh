from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import Channel, IncidentEpisode, User
from app.schemas.schemas import ChannelOut

router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ChannelOut])
def list_channels(
    object_id: int | None = None,
    sensor_type: str | None = None,
    search: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Channel]:
    """Реестр каналов — раздел «Объекты и каналы» админ-панели, отдельно от иерархической
    схемы рисков (объекты/tree): здесь плоский список для поиска/инвентаризации."""
    stmt = select(Channel)
    if object_id is not None:
        stmt = stmt.where(Channel.object_id == object_id)
    if sensor_type:
        stmt = stmt.where(Channel.sensor_type == sensor_type)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(Channel.display_name.ilike(pattern), Channel.location_tag.ilike(pattern))
        )
    accessible = get_accessible_object_ids(user, db)
    if accessible is not None:
        stmt = stmt.where(Channel.object_id.in_(accessible))
    stmt = stmt.order_by(Channel.id)
    return list(db.scalars(stmt.offset(offset).limit(limit)))


@router.get("/{channel_id}", response_model=ChannelOut)
def get_channel(channel_id: int, db: Session = Depends(get_db)) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Канал не найден")
    return ch


@router.get("/{channel_id}/episodes")
def get_channel_episodes(channel_id: int, db: Session = Depends(get_db)) -> list[dict]:
    """Текущая/прошлая неисправность — отдельно от прогноза (раздел 9.1 плана)."""
    episodes = db.scalars(
        select(IncidentEpisode)
        .where(IncidentEpisode.channel_id == channel_id)
        .order_by(IncidentEpisode.start_time.desc())
    )
    return [
        {
            "id": e.id,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "is_flapping_incident": e.is_flapping_incident,
            "left_censored": e.left_censored,
            "right_censored": e.right_censored,
        }
        for e in episodes
    ]
