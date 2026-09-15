from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.entities import Channel, IncidentEpisode
from app.schemas.schemas import ChannelOut

router = APIRouter(prefix="/channels", tags=["channels"], dependencies=[Depends(get_current_user)])


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
